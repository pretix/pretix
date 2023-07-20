#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import OrderedDict
from datetime import timezone

import bleach
import dateutil.parser
from django import forms
from django.db.models import (
    Case, Exists, F, Max, OuterRef, Q, Subquery, Value, When,
)
from django.db.models.functions import Coalesce, NullIf
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.timezone import is_aware, make_aware, now
from django.utils.translation import (
    gettext as _, gettext_lazy, pgettext, pgettext_lazy,
)
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from pretix.base.exporter import BaseExporter, ListExporter
from pretix.base.models import (
    Checkin, InvoiceAddress, Order, OrderPosition, Question,
)
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.templatetags.money import money_filter
from pretix.base.timeframes import (
    DateFrameField,
    resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
)
from pretix.control.forms.widgets import Select2
from pretix.helpers.filenames import safe_for_filename
from pretix.helpers.templatetags.jsonfield import JSONExtract
from pretix.plugins.reports.exporters import ReportlabExportMixin


class CheckInListMixin(BaseExporter):
    @property
    def _fields(self):
        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme]
        d = OrderedDict(
            [
                ('list',
                 forms.ModelChoiceField(
                     queryset=self.event.checkin_lists.all(),
                     label=_('Check-in list'),
                     widget=forms.RadioSelect(
                         attrs={'class': 'scrolling-choice'}
                     ),
                     initial=self.event.checkin_lists.first()
                 )),
                ('date_range',
                 DateFrameField(
                     label=_('Date range'),
                     include_future_frames=True,
                     required=False,
                     help_text=_('Only include tickets for dates within this range.')
                 )),
                ('secrets',
                 forms.BooleanField(
                     label=_('Include QR-code secret'),
                     required=False
                 )),
                ('attention_only',
                 forms.BooleanField(
                     label=_('Only tickets requiring special attention'),
                     required=False
                 )),
                ('status',
                 forms.ChoiceField(
                     label=_('Check-in status'),
                     choices=(
                         ('', _('All attendees')),
                         ('1', _('Checked in')),
                         ('2', pgettext_lazy('checkin state', 'Present')),
                         ('3', pgettext_lazy('checkin state', 'Checked in but left')),
                         ('0', _('Not checked in')),
                     ),
                     required=False,
                 )),
                ('sort',
                 forms.ChoiceField(
                     label=_('Sort by'),
                     initial='name',
                     choices=[
                         ('name', _('Attendee name')),
                         ('code', _('Order code')),
                     ] + ([
                         ('name:{}'.format(k), _('Attendee name: {part}').format(part=label))
                         for k, label, w in name_scheme['fields']
                     ] if len(name_scheme['fields']) > 1 else []),
                     widget=forms.RadioSelect,
                     required=False
                 )),
                ('questions',
                 forms.ModelMultipleChoiceField(
                     queryset=self.event.questions.all(),
                     label=_('Include questions'),
                     widget=forms.CheckboxSelectMultiple(
                         attrs={'class': 'scrolling-multiple-choice'}
                     ),
                     required=False
                 )),
            ]
        )

        if not self.event.has_subevents:
            del d['date_range']

        d['list'].queryset = self.event.checkin_lists.all()
        d['list'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.orders.checkinlists.select2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('Check-in list')
            }
        )
        d['list'].widget.choices = d['list'].choices
        d['list'].required = True

        return d

    def _get_queryset(self, cl, form_data):
        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=cl.pk
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')

        cqsin = cqs.filter(
            type=Checkin.TYPE_ENTRY
        )
        cqsout = cqs.filter(
            type=Checkin.TYPE_EXIT
        )

        qs = OrderPosition.objects.filter(
            order__event=self.event,
        ).annotate(
            last_checked_in=Subquery(cqsin),
            last_checked_out=Subquery(cqsout),
            auto_checked_in=Exists(
                Checkin.objects.filter(position_id=OuterRef('pk'), list_id=cl.pk, auto_checked_in=True)
            )
        ).prefetch_related(
            'answers', 'answers__question', 'addon_to__answers', 'addon_to__answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to', 'order__invoice_address', 'voucher', 'seat')

        if form_data.get('status'):
            s = form_data.get('status')
            if s == '1':
                qs = qs.filter(last_checked_in__isnull=False)
            elif s == '2':
                qs = qs.filter(pk__in=cl.positions_inside.values_list('pk'))
            elif s == '3':
                qs = qs.filter(last_checked_in__isnull=False).filter(
                    Q(last_checked_out__isnull=False) & Q(last_checked_out__gte=F('last_checked_in'))
                )
            elif s == '0':
                qs = qs.filter(last_checked_in__isnull=True)

        if not cl.all_products:
            qs = qs.filter(item__in=cl.limit_products.values_list('id', flat=True))

        if cl.subevent:
            qs = qs.filter(subevent=cl.subevent)

        if form_data.get('date_range'):
            dt_start, dt_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(now(), form_data['date_range'], self.timezone)
            if dt_start:
                qs = qs.filter(subevent__date_from__gte=dt_start)
            if dt_end:
                qs = qs.filter(subevent__date_from__lt=dt_end)

        o = ()
        if self.event.has_subevents and not cl.subevent:
            o = ('subevent__date_from', 'subevent__name')

        sort = form_data.get('sort') or 'name'
        if sort == 'name':
            qs = qs.order_by(
                *o,
                Coalesce(
                    NullIf('attendee_name_cached', Value('')),
                    NullIf('addon_to__attendee_name_cached', Value('')),
                    NullIf('order__invoice_address__name_cached', Value('')),
                    'order__code'
                )
            )
        elif sort == 'code':
            qs = qs.order_by(*o, 'order__code')
        elif sort.startswith('name:'):
            part = sort[5:]
            qs = qs.annotate(
                resolved_name=Case(
                    When(attendee_name_cached__ne='', then='attendee_name_parts'),
                    When(addon_to__attendee_name_cached__isnull=False, addon_to__attendee_name_cached__ne='', then='addon_to__attendee_name_parts'),
                    default='order__invoice_address__name_parts',
                )
            ).annotate(
                resolved_name_part=JSONExtract('resolved_name', part)
            ).order_by(
                *o,
                'resolved_name_part'
            )

        if form_data.get('attention_only'):
            qs = qs.filter(Q(item__checkin_attention=True) | Q(order__checkin_attention=True) | Q(variation__checkin_attention=True))

        if not cl.include_pending:
            qs = qs.filter(
                Q(order__status=Order.STATUS_PAID) |
                Q(order__status=Order.STATUS_PENDING, order__valid_if_pending=True)
            )
        else:
            qs = qs.filter(order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING))

        return qs


class CBFlowable(Flowable):
    def __init__(self, checked=False):
        self.checked = checked
        super().__init__()

    def draw(self):
        self.canv.rect(1 * mm, -4.5 * mm, 4 * mm, 4 * mm)
        if self.checked:
            self.canv.line(1.5 * mm, -4.0 * mm, 4.5 * mm, -1.0 * mm)
            self.canv.line(1.5 * mm, -1.0 * mm, 4.5 * mm, -4.0 * mm)


class TableTextRotate(Flowable):
    def __init__(self, text):
        Flowable.__init__(self)
        self.text = text

    def draw(self):
        canvas = self.canv
        canvas.rotate(90)
        canvas.drawString(0, -1, self.text)


class PDFCheckinList(ReportlabExportMixin, CheckInListMixin, BaseExporter):
    name = "overview"
    identifier = 'checkinlistpdf'
    verbose_name = gettext_lazy('Check-in list (PDF)')
    category = pgettext_lazy('export_category', 'Check-in')
    description = gettext_lazy("Download a PDF version of a check-in list that can be used to check people in at the "
                               "event without digital methods.")
    numbered_canvas = True

    @property
    def export_form_fields(self):
        f = self._fields
        del f['secrets']
        return f

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.landscape(pagesizes.A4)

    def get_story(self, doc, form_data):
        cl = self.event.checkin_lists.get(pk=form_data['list'])

        questions = list(Question.objects.filter(event=self.event, id__in=form_data['questions']))

        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        headlinestyle.fontName = 'OpenSansBd'
        colwidths = [3 * mm, 8 * mm, 8 * mm] + [
            a * (doc.width - 8 * mm)
            for a in [.1, .25, (.25 if questions else .60)] + (
                [.35 / len(questions)] * len(questions) if questions else []
            )
        ]
        tstyledata = [
            ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
            ('ALIGN', (2, 0), (2, 0), 'CENTER'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'OpenSansBd'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('TEXTCOLOR', (0, 0), (0, -1), '#990000'),
            ('FONTNAME', (0, 0), (0, -1), 'OpenSansBd'),
        ]

        story = [
            Paragraph(
                cl.name,
                headlinestyle
            ),
        ]
        if cl.subevent:
            story += [
                Spacer(1, 3 * mm),
                Paragraph(
                    '{} ({} {})'.format(
                        cl.subevent.name,
                        cl.subevent.get_date_range_display(),
                        date_format(cl.subevent.date_from.astimezone(self.timezone), 'TIME_FORMAT')
                    ),
                    self.get_style()
                ),
            ]

        story += [
            Spacer(1, 5 * mm)
        ]

        tdata = [
            [
                '',
                '',
                # Translators: maximum 5 characters
                TableTextRotate(pgettext('tablehead', 'paid')),
                _('Order'),
                _('Name'),
                _('Product') + ' / ' + _('Price'),
            ],
        ]

        headrowstyle = self.get_style()
        headrowstyle.fontName = 'OpenSansBd'
        for q in questions:
            txt = str(q.question)
            p = Paragraph(txt, headrowstyle)
            while p.wrap(colwidths[len(tdata[0])], 5000)[1] > 30 * mm:
                txt = txt[:len(txt) - 50] + "..."
                p = Paragraph(txt, headrowstyle)
            tdata[0].append(p)

        qs = self._get_queryset(cl, form_data)

        for op in qs:
            try:
                ian = op.order.invoice_address.name
                iac = op.order.invoice_address.company
            except:
                ian = ""
                iac = ""

            name = op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '') or ian
            if iac:
                name += "<br/>" + iac

            item = "{} ({})".format(
                str(op.item) + (" – " + str(op.variation.value) if op.variation else ""),
                money_filter(op.price, self.event.currency),
            )
            if self.event.has_subevents and not cl.subevent:
                item += '<br/>{} ({})'.format(
                    op.subevent.name,
                    date_format(op.subevent.date_from.astimezone(self.event.timezone), 'SHORT_DATETIME_FORMAT')
                )
            if op.seat:
                item += '<br/>' + str(op.seat)
            name = bleach.clean(str(name), tags=['br']).strip().replace('<br>', '<br/>')
            if op.blocked:
                name = '<font face="OpenSansBd">[' + _('Blocked') + ']</font> ' + name
            row = [
                '!!' if op.require_checkin_attention else '',
                CBFlowable(bool(op.last_checked_in)) if not op.blocked else '—',
                '✘' if op.order.status != Order.STATUS_PAID else '✔',
                op.order.code,
                Paragraph(name, self.get_style()),
                Paragraph(bleach.clean(str(item), tags=['br']).strip().replace('<br>', '<br/>'), self.get_style()),
            ]
            acache = {}
            if op.addon_to:
                for a in op.addon_to.answers.all():
                    # We do not want to localize Date, Time and Datetime question answers, as those can lead
                    # to difficulties parsing the data (for example 2019-02-01 may become Février, 2019 01 in French).
                    if a.question.type in Question.UNLOCALIZED_TYPES:
                        acache[a.question_id] = a.answer
                    else:
                        acache[a.question_id] = str(a)
            for a in op.answers.all():
                # We do not want to localize Date, Time and Datetime question answers, as those can lead
                # to difficulties parsing the data (for example 2019-02-01 may become Février, 2019 01 in French).
                if a.question.type in Question.UNLOCALIZED_TYPES:
                    acache[a.question_id] = a.answer
                else:
                    acache[a.question_id] = str(a)
            for q in questions:
                txt = acache.get(q.pk, '')
                txt = bleach.clean(txt, tags=['br']).strip().replace('<br>', '<br/>')
                p = Paragraph(txt, self.get_style())
                while p.wrap(colwidths[len(row)], 5000)[1] > 50 * mm:
                    txt = txt[:len(txt) - 50] + "..."
                    p = Paragraph(txt, self.get_style())
                row.append(p)
            if op.order.status != Order.STATUS_PAID:
                tstyledata += [
                    ('BACKGROUND', (2, len(tdata)), (2, len(tdata)), '#990000'),
                    ('TEXTCOLOR', (2, len(tdata)), (2, len(tdata)), '#ffffff'),
                    ('ALIGN', (2, len(tdata)), (2, len(tdata)), 'CENTER'),
                ]
            if op.blocked:
                tstyledata += [
                    ('BACKGROUND', (1, len(tdata)), (1, len(tdata)), '#990000'),
                    ('TEXTCOLOR', (1, len(tdata)), (1, len(tdata)), '#ffffff'),
                    ('ALIGN', (1, len(tdata)), (1, len(tdata)), 'CENTER'),
                ]
            tdata.append(row)

        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story


class CSVCheckinList(CheckInListMixin, ListExporter):
    name = "overview"
    identifier = 'checkinlist'
    verbose_name = gettext_lazy('Check-in list')
    category = pgettext_lazy('export_category', 'Check-in')
    description = gettext_lazy("Download a spreadsheet with all attendees that are included in a check-in list.")
    featured = True

    @property
    def additional_form_fields(self):
        return self._fields

    def iterate_list(self, form_data):
        self.cl = cl = self.event.checkin_lists.get(pk=form_data['list'])

        questions = list(Question.objects.filter(event=self.event, id__in=form_data['questions']))

        qs = self._get_queryset(cl, form_data)

        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme]
        headers = [
            _('Order code'),
            _('Attendee name'),
        ]
        if len(name_scheme['fields']) > 1:
            for k, label, w in name_scheme['fields']:
                headers.append(_('Attendee name: {part}').format(part=label))
        headers += [
            _('Product'), _('Price'), _('Checked in'), _('Checked out'), _('Automatically checked in')
        ]
        if not cl.include_pending:
            qs = qs.filter(
                Q(order__status=Order.STATUS_PAID) |
                Q(order__status=Order.STATUS_PENDING, order__valid_if_pending=True)
            )
        else:
            qs = qs.filter(order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING))
            headers.append(_('Paid'))

        if form_data['secrets']:
            headers.append(_('Secret'))

        headers.append(_('E-mail'))
        headers.append(_('Phone number'))

        if self.event.has_subevents:
            headers.append(pgettext('subevent', 'Date'))
            headers.append(_('Start date'))
            headers.append(_('End date'))

        for q in questions:
            headers.append(str(q.question))

        headers.append(_('Company'))
        headers.append(_('Voucher code'))
        headers.append(_('Order date'))
        headers.append(_('Order time'))
        headers.append(_('Requires special attention'))
        headers.append(_('Comment'))
        headers.append(_('Seat ID'))
        headers.append(_('Seat name'))
        headers.append(_('Seat zone'))
        headers.append(_('Seat row'))
        headers.append(_('Seat number'))
        headers.append(_('Blocked'))
        headers.append(_('Valid from'))
        headers.append(_('Valid until'))
        headers += [
            _('Address'),
            _('ZIP code'),
            _('City'),
            _('Country'),
            pgettext('address', 'State'),
        ]
        yield headers

        yield self.ProgressSetTotal(total=qs.count())

        for op in qs:
            try:
                ia = op.order.invoice_address
            except InvoiceAddress.DoesNotExist:
                ia = InvoiceAddress()

            last_checked_in = None
            if isinstance(op.last_checked_in, str):  # SQLite
                last_checked_in = dateutil.parser.parse(op.last_checked_in)
            elif op.last_checked_in:
                last_checked_in = op.last_checked_in
            if last_checked_in and not is_aware(last_checked_in):
                last_checked_in = make_aware(last_checked_in, timezone.utc)

            last_checked_out = None
            if isinstance(op.last_checked_out, str):  # SQLite
                last_checked_out = dateutil.parser.parse(op.last_checked_out)
            elif op.last_checked_out:
                last_checked_out = op.last_checked_out
            if last_checked_out and not is_aware(last_checked_out):
                last_checked_out = make_aware(last_checked_out, timezone.utc)

            row = [
                op.order.code,
                op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '') or ia.name,
            ]
            if len(name_scheme['fields']) > 1:
                for k, label, w in name_scheme['fields']:
                    v = (
                        op.attendee_name_parts or
                        (op.addon_to.attendee_name_parts if op.addon_to else {}) or
                        ia.name_parts
                    ).get(k, '')
                    if k == "salutation":
                        v = pgettext("person_name_salutation", v)

                    row.append(v)
            row += [
                str(op.item) + (" – " + str(op.variation.value) if op.variation else ""),
                op.price,
                date_format(last_checked_in.astimezone(self.event.timezone), 'SHORT_DATETIME_FORMAT')
                if last_checked_in else '',
                date_format(last_checked_out.astimezone(self.event.timezone), 'SHORT_DATETIME_FORMAT')
                if last_checked_out else '',
                _('Yes') if op.auto_checked_in else _('No'),
            ]
            if cl.include_pending:
                row.append(_('Yes') if op.order.status == Order.STATUS_PAID else _('No'))
            if form_data['secrets']:
                row.append(op.secret)
            row.append(op.attendee_email or (op.addon_to.attendee_email if op.addon_to else '') or op.order.email or '')
            row.append(str(op.order.phone) if op.order.phone else '')
            if self.event.has_subevents:
                row.append(str(op.subevent.name))
                row.append(date_format(op.subevent.date_from.astimezone(self.event.timezone), 'SHORT_DATETIME_FORMAT'))
                if op.subevent.date_to:
                    row.append(
                        date_format(op.subevent.date_to.astimezone(self.event.timezone), 'SHORT_DATETIME_FORMAT')
                    )
                else:
                    row.append('')
            acache = {}
            if op.addon_to:
                for a in op.addon_to.answers.all():
                    # We do not want to localize Date, Time and Datetime question answers, as those can lead
                    # to difficulties parsing the data (for example 2019-02-01 may become Février, 2019 01 in French).
                    if a.question.type in Question.UNLOCALIZED_TYPES:
                        acache[a.question_id] = a.answer
                    else:
                        acache[a.question_id] = str(a)
            for a in op.answers.all():
                # We do not want to localize Date, Time and Datetime question answers, as those can lead
                # to difficulties parsing the data (for example 2019-02-01 may become Février, 2019 01 in French).
                if a.question.type in Question.UNLOCALIZED_TYPES:
                    acache[a.question_id] = a.answer
                else:
                    acache[a.question_id] = str(a)
            for q in questions:
                row.append(acache.get(q.pk, ''))

            row.append(op.company or ia.company)
            row.append(op.voucher.code if op.voucher else "")
            row.append(op.order.datetime.astimezone(self.event.timezone).strftime('%Y-%m-%d'))
            row.append(op.order.datetime.astimezone(self.event.timezone).strftime('%H:%M:%S'))
            row.append(_('Yes') if op.require_checkin_attention else _('No'))
            row.append(op.order.comment or "")

            if op.seat:
                row += [
                    op.seat.seat_guid,
                    str(op.seat),
                    op.seat.zone_name,
                    op.seat.row_name,
                    op.seat.seat_number,
                ]
            else:
                row += ['', '', '', '', '']

            row += [
                _('Yes') if op.blocked else '',
                date_format(op.valid_from, 'SHORT_DATETIME_FORMAT') if op.valid_from else '',
                date_format(op.valid_until, 'SHORT_DATETIME_FORMAT') if op.valid_until else '',
                op.street or '',
                op.zipcode or '',
                op.city or '',
                op.country if op.country else '',
                op.state or '',
            ]

            yield row

    def get_filename(self):
        return '{}_checkin_{}'.format(self.event.slug, safe_for_filename(self.cl.name))


class CheckinLogList(ListExporter):
    name = "checkinlog"
    identifier = 'checkinlog'
    verbose_name = gettext_lazy('Check-in log (all scans)')
    category = pgettext_lazy('export_category', 'Check-in')
    description = gettext_lazy("Download a spreadsheet with one line for every scan that happened at your check-in "
                               "stations.")

    @property
    def additional_form_fields(self):
        return self._fields

    def iterate_list(self, form_data):
        yield [
            _('Date'),
            _('Time'),
            _('Check-in list'),
            _('Scan type'),
            _('Order code'),
            _('Position ID'),
            _('Secret'),
            _('Product'),
            _('Name'),
            _('Device'),
            _('Offline'),
            _('Offline override'),
            _('Automatically checked in'),
            _('Gate'),
            _('Result'),
            _('Error message'),
            _('Upload date'),
            _('Upload time'),
        ]

        qs = Checkin.all.filter(
            list__event=self.event,
        )
        if form_data.get('list'):
            qs = qs.filter(list_id=form_data.get('list'))
        if form_data.get('items'):
            if len(form_data['items']) != self.event.items.count():
                qs = qs.filter(Q(position__item_id__in=form_data['items']) | Q(raw_item_id__in=form_data['items']))
        if form_data.get('successful_only'):
            qs = qs.filter(successful=True)

        if form_data.get('date_range'):
            dt_start, dt_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(now(), form_data['date_range'], self.timezone)
            if dt_start:
                qs = qs.filter(datetime__gte=dt_start)
            if dt_end:
                qs = qs.filter(datetime__lt=dt_end)

        yield self.ProgressSetTotal(total=qs.count())

        qs = qs.select_related(
            'position__item', 'position__order', 'position__order__invoice_address', 'position', 'list', 'device',
            'raw_item'
        ).order_by(
            'datetime'
        )
        for ci in qs.iterator():
            if ci.position:
                try:
                    ia = ci.position.order.invoice_address
                except InvoiceAddress.DoesNotExist:
                    ia = InvoiceAddress()

            yield [
                date_format(ci.datetime.astimezone(self.timezone), 'SHORT_DATE_FORMAT'),
                date_format(ci.datetime.astimezone(self.timezone), 'TIME_FORMAT'),
                str(ci.list),
                ci.get_type_display(),
                ci.position.order.code if ci.position else '',
                ci.position.positionid if ci.position else '',
                ci.raw_barcode or ci.position.secret,
                str(ci.position.item) if ci.position else (str(ci.raw_item) if ci.raw_item else ''),
                (ci.position.attendee_name or ia.name) if ci.position else '',
                str(ci.device) if ci.device else '',
                _('Yes') if ci.force_sent is True else (_('No') if ci.force_sent is False else '?'),
                _('Yes') if ci.forced else _('No'),
                _('Yes') if ci.auto_checked_in else _('No'),
                str(ci.gate or ''),
                _('OK') if ci.successful else ci.get_error_reason_display(),
                ci.error_explanation or '',
                date_format(ci.created.astimezone(self.timezone), 'SHORT_DATE_FORMAT'),
                date_format(ci.created.astimezone(self.timezone), 'TIME_FORMAT'),
            ]

    def get_filename(self):
        return '{}_checkinlog'.format(self.event.slug)

    @property
    def _fields(self):
        d = OrderedDict(
            [
                ('list',
                 forms.ModelChoiceField(
                     queryset=self.event.checkin_lists.all(),
                     label=_('Check-in list'),
                     widget=forms.RadioSelect(
                         attrs={'class': 'scrolling-choice'}
                     ),
                 )),
                ('items',
                 forms.ModelMultipleChoiceField(
                     queryset=self.event.items.all(),
                     label=_('Limit to products'),
                     widget=forms.CheckboxSelectMultiple(
                         attrs={'class': 'scrolling-multiple-choice'}
                     ),
                     initial=self.event.items.all()
                 )),
                ('successful_only',
                 forms.BooleanField(
                     label=_('Successful scans only'),
                     initial=True,
                     required=False,
                 )),
                ('date_range',
                 DateFrameField(
                     label=_('Date range'),
                     include_future_frames=False,
                     required=False,
                 )),
            ]
        )

        d['list'].queryset = self.event.checkin_lists.all()
        d['list'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.orders.checkinlists.select2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('All check-in lists')
            }
        )
        d['list'].widget.choices = d['list'].choices
        d['list'].required = False

        return d
