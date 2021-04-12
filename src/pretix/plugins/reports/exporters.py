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
# This file contains Apache-licensed contributions copyrighted by: Flavia Bastos
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
import tempfile
from collections import OrderedDict, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytz
from dateutil.parser import parse
from django import forms
from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import models
from django.db.models import DateTimeField, Max, OuterRef, Subquery, Sum
from django.template.defaultfilters import floatformat
from django.utils.formats import date_format, localize
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import gettext as _, gettext_lazy, pgettext
from django_countries.fields import Country
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import PageBreak

from pretix.base.decimal import round_decimal
from pretix.base.exporter import BaseExporter, MultiSheetListExporter
from pretix.base.forms.widgets import DatePickerWidget
from pretix.base.models import Order, OrderPosition
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import OrderFee, OrderPayment
from pretix.base.services.stats import order_overview
from pretix.control.forms.filter import OverviewFilterForm


class ReportlabExportMixin:
    multiBuild = False  # noqa

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.portrait(pagesizes.A4)

    def render(self, form_data):
        self.form_data = form_data
        return 'report-%s.pdf' % self.event.slug, 'application/pdf', self.create(form_data)

    def get_filename(self):
        tz = pytz.timezone(self.event.settings.timezone)
        return "%s-%s.pdf" % (self.name, now().astimezone(tz).strftime("%Y-%m-%d-%H-%M-%S"))

    @staticmethod
    def register_fonts():
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont('OpenSans', finders.find('fonts/OpenSans-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('OpenSansIt', finders.find('fonts/OpenSans-Italic.ttf')))
        pdfmetrics.registerFont(TTFont('OpenSansBd', finders.find('fonts/OpenSans-Bold.ttf')))

    def get_doc_template(self):
        from reportlab.platypus import BaseDocTemplate

        return BaseDocTemplate

    def create(self, form_data):
        from reportlab.lib.units import mm
        from reportlab.platypus import PageTemplate

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            Report.register_fonts()
            doc = self.get_doc_template()(f.name, pagesize=self.pagesize,
                                          leftMargin=15 * mm,
                                          rightMargin=15 * mm,
                                          topMargin=20 * mm,
                                          bottomMargin=15 * mm)
            doc.addPageTemplates([
                PageTemplate(id='All', frames=self.get_frames(doc), onPage=self.on_page, pagesize=self.pagesize)
            ])
            if self.multiBuild:
                doc.multiBuild(self.get_story(doc, form_data))
            else:
                doc.build(self.get_story(doc, form_data))
            f.seek(0)
            return f.read()

    def get_frames(self, doc):
        from reportlab.platypus import Frame

        self.frame = Frame(doc.leftMargin, doc.bottomMargin,
                           doc.width,
                           doc.height,
                           leftPadding=0,
                           rightPadding=0,
                           topPadding=0,
                           bottomPadding=0,
                           id='normal')
        return [self.frame]

    def get_story(self, doc, form_data):
        return []

    def get_style(self):
        from reportlab.lib.styles import getSampleStyleSheet

        styles = getSampleStyleSheet()
        style = styles["Normal"]
        style.fontName = 'OpenSans'
        return style

    def on_page(self, canvas, doc):
        canvas.saveState()
        self.page_footer(canvas, doc)
        self.page_header(canvas, doc)
        canvas.restoreState()

    def page_footer(self, canvas, doc):
        from reportlab.lib.units import mm

        tz = get_current_timezone()
        canvas.setFont('OpenSans', 8)
        canvas.drawString(15 * mm, 10 * mm, _("Page %d") % (doc.page,))
        canvas.drawRightString(self.pagesize[0] - 15 * mm, 10 * mm,
                               _("Created: %s") % now().astimezone(tz).strftime("%d.%m.%Y %H:%M:%S"))

    def get_right_header_string(self):
        return settings.PRETIX_INSTANCE_NAME

    def get_left_header_string(self):
        if self.event.has_subevents:
            return "%s – %s" % (self.event.organizer.name, self.event.name)
        else:
            return "%s – %s – %s" % (self.event.organizer.name, self.event.name,
                                     self.event.get_date_range_display())

    def page_header(self, canvas, doc):
        from reportlab.lib.units import mm

        canvas.setFont('OpenSans', 10)
        canvas.drawString(15 * mm, self.pagesize[1] - 15 * mm, self.get_left_header_string())
        canvas.drawRightString(self.pagesize[0] - 15 * mm, self.pagesize[1] - 15 * mm,
                               self.get_right_header_string())
        canvas.setStrokeColorRGB(0, 0, 0)
        canvas.line(15 * mm, self.pagesize[1] - 17 * mm,
                    self.pagesize[0] - 15 * mm, self.pagesize[1] - 17 * mm)


class Report(ReportlabExportMixin, BaseExporter):
    name = "report"

    def verbose_name(self) -> str:
        raise NotImplementedError()

    def identifier(self) -> str:
        raise NotImplementedError()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class OverviewReport(Report):
    name = "overview"
    identifier = 'pdfreport'
    verbose_name = gettext_lazy('Order overview (PDF)')

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.landscape(pagesizes.A4)

    def get_story(self, doc, form_data):

        if form_data.get('date_from'):
            form_data['date_from'] = parse(form_data['date_from'])
        if form_data.get('date_until'):
            form_data['date_until'] = parse(form_data['date_until'])

        story = self._table_story(doc, form_data)
        if self.event.tax_rules.exists():
            story += [PageBreak()]
            story += self._table_story(doc, form_data, net=True)
        return story

    def _table_story(self, doc, form_data, net=False):
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        headlinestyle.fontName = 'OpenSansBd'
        colwidths = [
            a * doc.width for a in (
                1 - (0.05 + 0.075) * 6,
                0.05, .075,
                0.05, .075,
                0.05, .075,
                0.05, .075,
                0.05, .075,
                0.05, .075
            )
        ]
        tstyledata = [
            ('SPAN', (1, 0), (2, 0)),
            ('SPAN', (3, 0), (4, 0)),
            ('SPAN', (5, 0), (6, 1)),
            ('SPAN', (7, 0), (-1, 0)),
            ('SPAN', (7, 1), (8, 1)),
            ('SPAN', (9, 1), (10, 1)),
            ('SPAN', (11, 1), (12, 1)),
            ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
            ('ALIGN', (1, 2), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 1), 'OpenSansBd'),
            ('FONTNAME', (0, -1), (-1, -1), 'OpenSansBd'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('LINEBEFORE', (1, 0), (1, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (3, 0), (3, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (5, 0), (5, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (7, 0), (7, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (9, 1), (9, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (11, 1), (11, -1), 1, colors.lightgrey),
        ]
        tstyle = copy.copy(self.get_style())
        tstyle.fontSize = 8
        tstyle_bold = copy.copy(tstyle)
        tstyle_bold.fontSize = 8
        tstyle_bold.fontName = 'OpenSansBd'
        tstyle_th = copy.copy(tstyle_bold)
        tstyle_th.alignment = TA_CENTER
        story = [
            Paragraph(_('Orders by product') + ' ' + (_('(excl. taxes)') if net else _('(incl. taxes)')), headlinestyle),
            Spacer(1, 5 * mm)
        ]
        if form_data.get('date_axis'):
            story += [
                Paragraph(_('{axis} between {start} and {end}').format(
                    axis=dict(OverviewFilterForm(event=self.event).fields['date_axis'].choices)[form_data.get('date_axis')],
                    start=date_format(form_data.get('date_from'), 'SHORT_DATE_FORMAT') if form_data.get('date_from') else '–',
                    end=date_format(form_data.get('date_until'), 'SHORT_DATE_FORMAT') if form_data.get('date_until') else '–',
                ), self.get_style()),
                Spacer(1, 5 * mm)
            ]

        if form_data.get('subevent'):
            try:
                subevent = self.event.subevents.get(pk=self.form_data.get('subevent'))
            except SubEvent.DoesNotExist:
                subevent = self.form_data.get('subevent')
            story.append(Paragraph(pgettext('subevent', 'Date: {}').format(subevent), self.get_style()))
            story.append(Spacer(1, 5 * mm))
        tdata = [
            [
                _('Product'),
                Paragraph(_('Canceled'), tstyle_th),
                '',
                Paragraph(_('Expired'), tstyle_th),
                '',
                Paragraph(_('Approval pending'), tstyle_th),
                '',
                Paragraph(_('Purchased'), tstyle_th),
                '', '', '', '', ''
            ],
            [
                '', '', '', '', '', '', '', _('Pending'), '', _('Paid'), '', _('Total'), ''
            ],
            [
                '',
                _('#'), self.event.currency,
                _('#'), self.event.currency,
                _('#'), self.event.currency,
                _('#'), self.event.currency,
                _('#'), self.event.currency,
                _('#'), self.event.currency,
            ],
        ]

        items_by_category, total = order_overview(
            self.event,
            subevent=form_data.get('subevent'),
            date_filter=form_data.get('date_axis'),
            date_from=form_data.get('date_from'),
            date_until=form_data.get('date_until'),
            fees=True
        )
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
        states = (
            ('canceled', Order.STATUS_CANCELED),
            ('expired', Order.STATUS_EXPIRED),
            ('unapproved', 'unapproved'),
            ('pending', Order.STATUS_PENDING),
            ('paid', Order.STATUS_PAID),
            ('total', None),
        )

        for tup in items_by_category:
            if tup[0]:
                tdata.append([
                    Paragraph(str(tup[0].name), tstyle_bold)
                ])
                for l, s in states:
                    tdata[-1].append(str(tup[0].num[l][0]))
                    tdata[-1].append(floatformat(tup[0].num[l][2 if net else 1], places))
            for item in tup[1]:
                tdata.append([
                    str(item)
                ])
                for l, s in states:
                    tdata[-1].append(str(item.num[l][0]))
                    tdata[-1].append(floatformat(item.num[l][2 if net else 1], places))
                if item.has_variations:
                    for var in item.all_variations:
                        tdata.append([
                            Paragraph("          " + str(var), tstyle)
                        ])
                        for l, s in states:
                            tdata[-1].append(str(var.num[l][0]))
                            tdata[-1].append(floatformat(var.num[l][2 if net else 1], places))

        tdata.append([
            _("Total"),
        ])
        for l, s in states:
            tdata[-1].append(str(total['num'][l][0]))
            tdata[-1].append(floatformat(total['num'][l][2 if net else 1], places))

        table = Table(tdata, colWidths=colwidths, repeatRows=3)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story

    @property
    def export_form_fields(self) -> dict:
        f = OverviewFilterForm(event=self.event)
        del f.fields['ordering']
        return f.fields


class OrderTaxListReportPDF(Report):
    name = "ordertaxlist"
    identifier = 'ordertaxes'
    verbose_name = gettext_lazy('List of orders with taxes (PDF)')

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('status',
                 forms.MultipleChoiceField(
                     label=gettext_lazy('Filter by status'),
                     initial=[Order.STATUS_PAID],
                     choices=Order.STATUS_CHOICE,
                     widget=forms.CheckboxSelectMultiple,
                     required=False
                 )),
                ('sort',
                 forms.ChoiceField(
                     label=gettext_lazy('Sort by'),
                     initial='datetime',
                     choices=(
                         ('datetime', gettext_lazy('Order date')),
                         ('payment_date', gettext_lazy('Payment date')),
                     ),
                     widget=forms.RadioSelect,
                     required=False
                 )),
            ]
        )

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.landscape(pagesizes.A4)

    def get_story(self, doc, form_data):
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        headlinestyle.fontName = 'OpenSansBd'
        tz = pytz.timezone(self.event.settings.timezone)

        tax_rates = set(
            a for a
            in OrderFee.objects.filter(
                order__event=self.event
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates |= set(
            a for a
            in OrderPosition.objects.filter(order__event=self.event).filter(
                order__status__in=self.form_data['status']
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates = sorted(tax_rates)

        # Cols: Order ID | Order date | Status | Payment Date | Total | {gross tax} for t in taxes
        colwidths = [a * doc.width for a in [0.12, 0.1, 0.10, 0.12, 0.08]]
        if tax_rates:
            colwidths += [0.48 / (len(tax_rates) * 2) * doc.width] * (len(tax_rates) * 2)

        tstyledata = [
            # Alignment
            ('ALIGN', (0, 0), (3, 0), 'LEFT'),  # Headlines
            ('ALIGN', (4, 0), (-1, 0), 'CENTER'),  # Headlines
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),  # Money
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

            # Fonts
            ('FONTNAME', (0, 0), (-1, 0), 'OpenSansBd'),  # Headlines
            ('FONTNAME', (0, -1), (-1, -1), 'OpenSansBd'),  # Sums
        ]
        for i, rate in enumerate(tax_rates):
            tstyledata.append(('SPAN', (5 + 2 * i, 0), (6 + 2 * i, 0)))

        story = [
            Paragraph(_('Orders by tax rate ({currency})').format(currency=self.event.currency), headlinestyle),
            Spacer(1, 5 * mm)
        ]
        tdata = [
            [
                _('Order code'), _('Order date'), _('Status'), _('Payment date'), _('Order total'),
            ] + sum(([localize(t) + ' %', ''] for t in tax_rates), []),
            [
                '', '', '', '', ''
            ] + sum(([_('Gross'), _('Tax')] for t in tax_rates), []),
        ]

        op_date = OrderPayment.objects.filter(
            order=OuterRef('order'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()
        qs = OrderPosition.objects.filter(
            order__status__in=self.form_data['status'],
            order__event=self.event,
        ).annotate(payment_date=Subquery(op_date, output_field=models.DateTimeField())).values(
            'order__code', 'order__datetime', 'payment_date', 'order__total', 'tax_rate', 'order__status',
            'order__id'
        ).annotate(prices=Sum('price'), tax_values=Sum('tax_value')).order_by(
            'order__datetime' if self.form_data['sort'] == 'datetime' else 'payment_date',
            'order__datetime',
            'order__code'
        )
        fee_sum_cache = {
            (o['order__id'], o['tax_rate']): o for o in
            OrderFee.objects.values('tax_rate', 'order__id').order_by().annotate(
                taxsum=Sum('tax_value'), grosssum=Sum('value')
            )
        }

        last_order_code = None
        tax_sums = defaultdict(Decimal)
        price_sums = defaultdict(Decimal)
        status_labels = dict(Order.STATUS_CHOICE)
        for op in qs:
            if op['order__code'] != last_order_code:
                tdata.append(
                    [
                        op['order__code'],
                        date_format(op['order__datetime'].astimezone(tz), "SHORT_DATE_FORMAT"),
                        status_labels[op['order__status']],
                        date_format(op['payment_date'], "SHORT_DATE_FORMAT") if op['payment_date'] else '',
                        op['order__total']
                    ] + sum((['', ''] for t in tax_rates), []),
                )
                last_order_code = op['order__code']
                for i, rate in enumerate(tax_rates):
                    odata = fee_sum_cache.get((op['order__id'], rate))
                    if odata:
                        tdata[-1][5 + 2 * i] = odata['grosssum'] or Decimal('0.00')
                        tdata[-1][6 + 2 * i] = odata['taxsum'] or Decimal('0.00')
                        tax_sums[rate] += odata['taxsum'] or Decimal('0.00')
                        price_sums[rate] += odata['grosssum'] or Decimal('0.00')

            i = tax_rates.index(op['tax_rate'])
            tdata[-1][5 + 2 * i] = (tdata[-1][5 + 2 * i] or Decimal('0.00')) + op['prices']
            tdata[-1][6 + 2 * i] = (tdata[-1][6 + 2 * i] or Decimal('0.00')) + op['tax_values']
            tax_sums[op['tax_rate']] += op['tax_values']
            price_sums[op['tax_rate']] += op['prices']

        tdata.append(
            [
                _('Total'), '', '', '', ''
            ] + sum(([
                price_sums.get(t) or Decimal('0.00'),
                tax_sums.get(t) or Decimal('0.00')
            ] for t in tax_rates), []),
        )
        tdata = [
            [
                localize(round_decimal(c, self.event.currency))
                if isinstance(c, (Decimal, int, float))
                else c
                for c in row
            ] for row in tdata
        ]

        table = Table(tdata, colWidths=colwidths, repeatRows=2)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story


class OrderTaxListReport(MultiSheetListExporter):
    identifier = 'ordertaxeslist'
    verbose_name = gettext_lazy('List of orders with taxes')

    @property
    def sheets(self):
        return (
            ('orders', _('Orders')),
            ('countries', _('Taxes by country')),
            ('companies', _('Business customers')),
        )

    @property
    def export_form_fields(self):
        f = super().export_form_fields
        f.update(OrderedDict(
            [
                ('status',
                 forms.MultipleChoiceField(
                     label=_('Filter by status'),
                     initial=[Order.STATUS_PAID],
                     choices=Order.STATUS_CHOICE,
                     widget=forms.CheckboxSelectMultiple,
                     required=False
                 )),
                ('sort',
                 forms.ChoiceField(
                     label=_('Sort by'),
                     initial='datetime',
                     choices=(
                         ('datetime', gettext_lazy('Order date')),
                         ('payment_date', gettext_lazy('Payment date')),
                     ),
                     widget=forms.RadioSelect,
                     required=False
                 )),
                ('date_axis',
                 forms.ChoiceField(
                     label=_('Date filter'),
                     choices=(
                         ('', _('Filter by…')),
                         ('order_date', _('Order date')),
                         ('last_payment_date', _('Date of last successful payment')),
                     ),
                     required=False,
                 )),
                ('date_from', forms.DateField(
                    label=_('Date from'),
                    required=False,
                    widget=DatePickerWidget,
                )),
                ('date_until', forms.DateField(
                    label=_('Date until'),
                    required=False,
                    widget=DatePickerWidget,
                ))
            ]
        ))
        return f

    def filter_qs(self, qs, form_data):
        date_from = form_data.get('date_from')
        date_until = form_data.get('date_until')
        date_filter = form_data.get('date_axis')
        if date_from:
            if isinstance(date_from, str):
                date_from = parse(date_from).date()
            if isinstance(date_from, date):
                date_from = make_aware(datetime.combine(
                    date_from,
                    time(hour=0, minute=0, second=0, microsecond=0)
                ), self.event.timezone)

        if date_until:
            if isinstance(date_until, str):
                date_until = parse(date_until).date()
            if isinstance(date_until, date):
                date_until = make_aware(datetime.combine(
                    date_until + timedelta(days=1),
                    time(hour=0, minute=0, second=0, microsecond=0)
                ), self.event.timezone)

        if date_filter == 'order_date':
            if date_from:
                qs = qs.filter(order__datetime__gte=date_from)
            if date_until:
                qs = qs.filter(order__datetime__lt=date_until)
        elif date_filter == 'last_payment_date':
            p_date = OrderPayment.objects.filter(
                order=OuterRef('order'),
                state__in=[OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED],
                payment_date__isnull=False
            ).values('order').annotate(
                m=Max('payment_date')
            ).values('m').order_by()
            qs = qs.annotate(payment_date=Subquery(p_date, output_field=DateTimeField()))
            if date_from:
                qs = qs.filter(payment_date__gte=date_from)
            if date_until:
                qs = qs.filter(payment_date__lt=date_until)
        return qs

    def iterate_sheet(self, form_data, sheet):
        if sheet == 'orders':
            yield from self.iterate_orders(form_data)
        elif sheet == 'countries':
            yield from self.iterate_countries(form_data)
        elif sheet == 'companies':
            yield from self.iterate_companies(form_data)

    def _combine(self, *qs, keys=()):
        cache = {}

        def kf(r):
            return tuple(r[k] for k in keys)

        for q in qs:
            for r in q:
                if kf(r) not in cache:
                    cache[kf(r)] = {
                        'prices': Decimal('0.00'),
                        'tax_values': Decimal('0.00'),
                    }
                cache[kf(r)]['prices'] += (r['prices'] or Decimal('0.00'))
                cache[kf(r)]['tax_values'] += (r['tax_values'] or Decimal('0.00'))

        return [
            dict(**{kname: k[i] for i, kname in enumerate(keys)}, **v)
            for k, v in sorted(
                cache.items(),
                key=lambda item: (
                    tuple(
                        ((iv or Decimal('0.00')) if keys[i] == 'tax_rate' else (iv or ''))
                        for i, iv in enumerate(item[0])
                    )
                )
            )
        ]

    def iterate_countries(self, form_data):
        keys = (
            'order__invoice_address__country',
            'tax_rate',
        )
        opqs = self.filter_qs(OrderPosition.objects, form_data).filter(
            order__status__in=form_data['status'],
            order__event=self.event,
        ).values(*keys).annotate(
            prices=Sum('price'),
            tax_values=Sum('tax_value')
        )
        ofqs = self.filter_qs(OrderFee.objects, form_data).filter(
            order__status__in=form_data['status'],
            order__event=self.event,
        ).values(*keys).annotate(
            prices=Sum('value'),
            tax_values=Sum('tax_value')
        )
        yield [
            _('Country code'),
            _('Country'),
            _('Tax rate'),
            _('Gross'),
            _('Tax')
        ]
        res = self._combine(opqs, ofqs, keys=keys)
        for r in res:
            yield [
                str(r['order__invoice_address__country']),
                Country(r['order__invoice_address__country']).name,
                r['tax_rate'],
                r['prices'],
                r['tax_values'],
            ]

    def iterate_companies(self, form_data):
        keys = (
            'order__invoice_address__country',
            'tax_rate',
            'order__invoice_address__company',
            'order__invoice_address__street',
            'order__invoice_address__zipcode',
            'order__invoice_address__city',
            'order__invoice_address__state',
            'order__invoice_address__vat_id',
            'order__invoice_address__custom_field',
        )
        opqs = self.filter_qs(OrderPosition.objects, form_data).filter(
            order__status__in=form_data['status'],
            order__event=self.event,
            order__invoice_address__is_business=True,
        ).values(*keys).annotate(
            prices=Sum('price'),
            tax_values=Sum('tax_value')
        )
        ofqs = self.filter_qs(OrderFee.objects, form_data).filter(
            order__status__in=form_data['status'],
            order__event=self.event,
            order__invoice_address__is_business=True,
        ).values(*keys).annotate(
            prices=Sum('value'),
            tax_values=Sum('tax_value')
        )
        yield [
            _('Country code'),
            _('Country'),
            _('Tax rate'),
            _('Company'),
            _('Address'),
            _('ZIP code'),
            _('City'),
            pgettext('address', 'State'),
            _('VAT ID'),
            self.event.settings.invoice_address_custom_field or 'Custom field',
            _('Gross'),
            _('Tax')
        ]
        res = self._combine(opqs, ofqs, keys=keys)
        for r in res:
            yield [
                str(r['order__invoice_address__country']),
                Country(r['order__invoice_address__country']).name,
                r['tax_rate'],
                r['order__invoice_address__company'],
                r['order__invoice_address__street'],
                r['order__invoice_address__zipcode'],
                r['order__invoice_address__city'],
                r['order__invoice_address__state'],
                r['order__invoice_address__vat_id'],
                r['order__invoice_address__custom_field'],
                r['prices'],
                r['tax_values'],
            ]

    def iterate_orders(self, form_data):
        tz = self.event.timezone

        tax_rates = set(
            a for a
            in OrderFee.objects.filter(
                order__event=self.event
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates |= set(
            a for a
            in OrderPosition.objects.filter(order__event=self.event).filter(
                order__status__in=form_data['status']
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates = sorted(tax_rates)

        headers = [
            _('Order code'), _('Order date'),
            _('Company'), _('Name'),
            _('Country'), _('VAT ID'), _('Status'), _('Payment date'), _('Order total'),
        ] + sum(([str(t) + ' % ' + _('Gross'), str(t) + ' % ' + _('Tax')] for t in tax_rates), [])
        yield headers

        op_date = OrderPayment.objects.filter(
            order=OuterRef('order'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()
        qs = self.filter_qs(OrderPosition.objects, form_data).filter(
            order__status__in=form_data['status'],
            order__event=self.event,
        ).annotate(payment_date=Subquery(op_date, output_field=models.DateTimeField())).values(
            'order__code', 'order__datetime', 'payment_date', 'order__total', 'tax_rate', 'order__status',
            'order__id', 'order__invoice_address__name_cached', 'order__invoice_address__company',
            'order__invoice_address__country', 'order__invoice_address__vat_id'
        ).annotate(prices=Sum('price'), tax_values=Sum('tax_value')).order_by(
            'order__datetime' if form_data['sort'] == 'datetime' else 'payment_date',
            'order__datetime',
            'order__code'
        )
        fee_sum_cache = {
            (o['order__id'], o['tax_rate']): o for o in
            OrderFee.objects.values('tax_rate', 'order__id').order_by().annotate(
                taxsum=Sum('tax_value'), grosssum=Sum('value')
            )
        }

        last_order_code = None
        tax_sums = defaultdict(Decimal)
        price_sums = defaultdict(Decimal)
        status_labels = dict(Order.STATUS_CHOICE)
        row = None
        for op in qs:
            if op['order__code'] != last_order_code:
                if row:
                    yield row
                    row = None
                row = [
                    op['order__code'],
                    date_format(op['order__datetime'].astimezone(tz), "SHORT_DATE_FORMAT"),
                    op['order__invoice_address__company'],
                    op['order__invoice_address__name_cached'],
                    op['order__invoice_address__country'],
                    op['order__invoice_address__vat_id'],
                    status_labels[op['order__status']],
                    date_format(op['payment_date'], "SHORT_DATE_FORMAT") if op['payment_date'] else '',
                    round_decimal(op['order__total'], self.event.currency),
                ] + sum(([Decimal('0.00'), Decimal('0.00')] for t in tax_rates), [])
                last_order_code = op['order__code']
                for i, rate in enumerate(tax_rates):
                    odata = fee_sum_cache.get((op['order__id'], rate))
                    if odata:
                        row[9 + 2 * i] = odata['grosssum'] or 0
                        row[10 + 2 * i] = odata['taxsum'] or 0
                        tax_sums[rate] += odata['taxsum'] or 0
                        price_sums[rate] += odata['grosssum'] or 0

            i = tax_rates.index(op['tax_rate'])
            row[9 + 2 * i] = round_decimal(row[9 + 2 * i] + op['prices'], self.event.currency)
            row[10 + 2 * i] = round_decimal(row[10 + 2 * i] + op['tax_values'], self.event.currency)
            tax_sums[op['tax_rate']] += op['tax_values']
            price_sums[op['tax_rate']] += op['prices']

        if row:
            yield row
        yield [
            _('Total'), '', '', '', '', '', '', '', ''
        ] + sum(([
            round_decimal(price_sums.get(t) or Decimal('0.00'), self.event.currency),
            round_decimal(tax_sums.get(t) or Decimal('0.00'), self.event.currency)
        ] for t in tax_rates), [])
