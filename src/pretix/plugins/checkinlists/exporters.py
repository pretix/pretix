from collections import OrderedDict

import dateutil.parser
from django import forms
from django.conf import settings
from django.db.models import Max, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.timezone import is_aware, make_aware
from django.utils.translation import pgettext, ugettext as _, ugettext_lazy
from jsonfallback.functions import JSONExtract
from pytz import UTC
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from pretix.base.exporter import BaseExporter, ListExporter
from pretix.base.models import (
    Checkin, InvoiceAddress, Order, OrderPosition, Question,
)
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.templatetags.money import money_filter
from pretix.control.forms.widgets import Select2
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
                ('secrets',
                 forms.BooleanField(
                     label=_('Include QR-code secret'),
                     required=False
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
                     ] if settings.JSON_FIELD_AVAILABLE and len(name_scheme['fields']) > 1 else []),
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
        qs = OrderPosition.objects.filter(
            order__event=self.event,
        ).annotate(
            last_checked_in=Subquery(cqs)
        ).prefetch_related(
            'answers', 'answers__question', 'addon_to__answers', 'addon_to__answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to', 'order__invoice_address', 'voucher')

        if not cl.all_products:
            qs = qs.filter(item__in=cl.limit_products.values_list('id', flat=True))

        if cl.subevent:
            qs = qs.filter(subevent=cl.subevent)

        if form_data['sort'] == 'name':
            qs = qs.order_by(Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached', 'order__invoice_address__name_cached'),
                             'order__code')
        elif form_data['sort'] == 'code':
            qs = qs.order_by('order__code')
        elif form_data['sort'].startswith('name:'):
            part = form_data['sort'][5:]
            qs = qs.annotate(
                resolved_name=Coalesce('attendee_name_parts', 'addon_to__attendee_name_parts', 'order__invoice_address__name_parts')
            ).annotate(
                resolved_name_part=JSONExtract('resolved_name', part)
            ).order_by(
                'resolved_name_part'
            )

        if not cl.include_pending:
            qs = qs.filter(order__status=Order.STATUS_PAID)
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
    verbose_name = ugettext_lazy('Check-in list (PDF)')

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
                _('Product') + '\n' + _('Price'),
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

            row = [
                '!!' if op.item.checkin_attention else '',
                CBFlowable(bool(op.last_checked_in)),
                '✘' if op.order.status != Order.STATUS_PAID else '✔',
                op.order.code,
                Paragraph(name, self.get_style()),
                Paragraph(str(op.item) + (" – " + str(op.variation.value) if op.variation else "") + "<br/>" +
                          money_filter(op.price, self.event.currency), self.get_style()),
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
            tdata.append(row)

        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story


class CSVCheckinList(CheckInListMixin, ListExporter):
    name = "overview"
    identifier = 'checkinlist'
    verbose_name = ugettext_lazy('Check-in list')

    @property
    def additional_form_fields(self):
        return self._fields

    def iterate_list(self, form_data):
        cl = self.event.checkin_lists.get(pk=form_data['list'])

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
            _('Product'), _('Price'), _('Checked in')
        ]
        if not cl.include_pending:
            qs = qs.filter(order__status=Order.STATUS_PAID)
        else:
            qs = qs.filter(order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING))
            headers.append(_('Paid'))

        if form_data['secrets']:
            headers.append(_('Secret'))

        headers.append(_('E-mail'))

        if self.event.has_subevents:
            headers.append(pgettext('subevent', 'Date'))

        for q in questions:
            headers.append(str(q.question))

        headers.append(_('Company'))
        headers.append(_('Voucher code'))
        headers.append(_('Order date'))
        yield headers

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
                last_checked_in = make_aware(last_checked_in, UTC)
            row = [
                op.order.code,
                op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '') or ia.name,
            ]
            if len(name_scheme['fields']) > 1:
                for k, label, w in name_scheme['fields']:
                    row.append(
                        (
                            op.attendee_name_parts or
                            (op.addon_to.attendee_name_parts if op.addon_to else {}) or
                            ia.name_parts
                        ).get(k, '')
                    )
            row += [
                str(op.item) + (" – " + str(op.variation.value) if op.variation else ""),
                op.price,
                date_format(last_checked_in.astimezone(self.event.timezone), 'SHORT_DATETIME_FORMAT')
                if last_checked_in else ''
            ]
            if cl.include_pending:
                row.append(_('Yes') if op.order.status == Order.STATUS_PAID else _('No'))
            if form_data['secrets']:
                row.append(op.secret)
            row.append(op.attendee_email or (op.addon_to.attendee_email if op.addon_to else '') or op.order.email or '')
            if self.event.has_subevents:
                row.append(str(op.subevent))
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

            row.append(ia.company)
            row.append(op.voucher.code if op.voucher else "")
            row.append(op.order.datetime.astimezone(self.event.timezone).strftime('%Y-%m-%d'))
            yield row

    def get_filename(self):
        return '{}_checkin'.format(self.event.slug)
