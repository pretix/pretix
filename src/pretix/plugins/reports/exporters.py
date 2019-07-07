import tempfile
from collections import OrderedDict, defaultdict
from decimal import Decimal

import pytz
from dateutil.parser import parse
from django import forms
from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import models
from django.db.models import Max, OuterRef, Subquery, Sum
from django.template.defaultfilters import floatformat
from django.utils.formats import date_format, localize
from django.utils.timezone import get_current_timezone, now
from django.utils.translation import pgettext, ugettext as _
from reportlab.lib import colors

from pretix.base.decimal import round_decimal
from pretix.base.exporter import BaseExporter
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
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase import pdfmetrics

        pdfmetrics.registerFont(TTFont('OpenSans', finders.find('fonts/OpenSans-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('OpenSansIt', finders.find('fonts/OpenSans-Italic.ttf')))
        pdfmetrics.registerFont(TTFont('OpenSansBd', finders.find('fonts/OpenSans-Bold.ttf')))

    def get_doc_template(self):
        from reportlab.platypus import BaseDocTemplate

        return BaseDocTemplate

    def create(self, form_data):
        from reportlab.platypus import PageTemplate
        from reportlab.lib.units import mm

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

    def __init__(self, event):
        super().__init__(event)


class OverviewReport(Report):
    name = "overview"
    identifier = 'pdfreport'
    verbose_name = _('Order overview (PDF)')

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.landscape(pagesizes.A4)

    def get_story(self, doc, form_data):
        from reportlab.platypus import Paragraph, Spacer, TableStyle, Table
        from reportlab.lib.units import mm

        if form_data.get('date_from'):
            form_data['date_from'] = parse(form_data['date_from'])
        if form_data.get('date_until'):
            form_data['date_until'] = parse(form_data['date_until'])

        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        headlinestyle.fontName = 'OpenSansBd'
        colwidths = [
            a * doc.width for a in (.33, 0.05, .075, 0.05, .075, 0.05, .075, 0.05, .075, 0.05, .075)
        ]
        tstyledata = [
            ('SPAN', (1, 0), (2, 0)),
            ('SPAN', (3, 0), (4, 0)),
            ('SPAN', (5, 0), (-1, 0)),
            ('SPAN', (5, 1), (6, 1)),
            ('SPAN', (7, 1), (8, 1)),
            ('SPAN', (9, 1), (10, 1)),
            ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
            ('ALIGN', (1, 2), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 1), 'OpenSansBd'),
            ('FONTNAME', (0, -1), (-1, -1), 'OpenSansBd'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('LINEBEFORE', (1, 0), (1, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (3, 0), (3, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (5, 0), (5, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (7, 1), (7, -1), 1, colors.lightgrey),
            ('LINEBEFORE', (9, 1), (9, -1), 1, colors.lightgrey),
        ]

        story = [
            Paragraph(_('Orders by product'), headlinestyle),
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
                _('Product'), _('Canceled'), '', _('Expired'), '', _('Purchased'),
                '', '', '', '', ''
            ],
            [
                '', '', '', '', '', _('Pending'), '', _('Paid'), '', _('Total'), ''
            ],
            [
                '',
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
        )
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
        states = (
            ('canceled', Order.STATUS_CANCELED),
            ('expired', Order.STATUS_EXPIRED),
            ('pending', Order.STATUS_PENDING),
            ('paid', Order.STATUS_PAID),
            ('total', None),
        )

        for tup in items_by_category:
            if tup[0]:
                tstyledata.append(('FONTNAME', (0, len(tdata)), (-1, len(tdata)), 'OpenSansBd'))
                tdata.append([
                    tup[0].name,
                ])
                for l, s in states:
                    tdata[-1].append(str(tup[0].num[l][0]))
                    tdata[-1].append(floatformat(tup[0].num[l][1], places))
            for item in tup[1]:
                tdata.append([
                    str(item)
                ])
                for l, s in states:
                    tdata[-1].append(str(item.num[l][0]))
                    tdata[-1].append(floatformat(item.num[l][1], places))
                if item.has_variations:
                    for var in item.all_variations:
                        tdata.append([
                            "          " + str(var),
                        ])
                        for l, s in states:
                            tdata[-1].append(str(var.num[l][0]))
                            tdata[-1].append(floatformat(var.num[l][1], places))

        tdata.append([
            _("Total"),
        ])
        for l, s in states:
            tdata[-1].append(str(total['num'][l][0]))
            tdata[-1].append(floatformat(total['num'][l][1], places))

        table = Table(tdata, colWidths=colwidths, repeatRows=3)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story

    @property
    def export_form_fields(self) -> dict:
        f = OverviewFilterForm(event=self.event)
        del f.fields['ordering']
        return f.fields


class OrderTaxListReport(Report):
    name = "ordertaxlist"
    identifier = 'ordertaxes'
    verbose_name = _('List of orders with taxes (PDF)')

    @property
    def export_form_fields(self):
        return OrderedDict(
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
                         ('datetime', _('Order date')),
                         ('payment_date', _('Payment date')),
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
        from reportlab.platypus import Paragraph, Spacer, TableStyle, Table
        from reportlab.lib.units import mm

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
            ] + sum(([str(t) + ' %', ''] for t in tax_rates), []),
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
                        localize(round_decimal(op['order__total'], self.event.currency))
                    ] + sum((['', ''] for t in tax_rates), []),
                )
                last_order_code = op['order__code']
                for i, rate in enumerate(tax_rates):
                    odata = fee_sum_cache.get((op['order__id'], rate))
                    if odata:
                        tdata[-1][5 + 2 * i] = str(odata['grosssum'] or 0)
                        tdata[-1][6 + 2 * i] = str(odata['taxsum'] or 0)
                        tax_sums[rate] += odata['taxsum'] or 0
                        price_sums[rate] += odata['grosssum'] or 0

                i = tax_rates.index(op['tax_rate'])
                tdata[-1][5 + 2 * i] = localize(
                    round_decimal(Decimal(tdata[-1][5 + 2 * i] or '0') + op['prices'], self.event.currency))
                tdata[-1][6 + 2 * i] = localize(
                    round_decimal(Decimal(tdata[-1][6 + 2 * i] or '0') + op['tax_values'], self.event.currency))
                tax_sums[op['tax_rate']] += op['tax_values']
                price_sums[op['tax_rate']] += op['prices']

        tdata.append(
            [
                _('Total'), '', '', '', ''
            ] + sum(([
                localize(round_decimal(price_sums.get(t) or Decimal('0.00'), self.event.currency)),
                localize(round_decimal(tax_sums.get(t) or Decimal('0.00'), self.event.currency))
            ] for t in tax_rates), []),
        )

        table = Table(tdata, colWidths=colwidths, repeatRows=2)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story
