import tempfile
from collections import OrderedDict, defaultdict
from decimal import Decimal

import pytz
from django import forms
from django.conf import settings
from django.contrib.staticfiles import finders
from django.db.models import Sum
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.exporter import BaseExporter
from pretix.base.models import Order, OrderPosition
from pretix.base.services.stats import order_overview


class Report(BaseExporter):
    name = "report"

    def verbose_name(self) -> str:
        raise NotImplementedError()

    def identifier(self) -> str:
        raise NotImplementedError()

    def __init__(self, event):
        super().__init__(event)

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.portrait(pagesizes.A4)

    def render(self, form_data):
        self.form_data = form_data
        return 'report-%s.pdf' % self.event.slug, 'application/pdf', self.create()

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

    def create(self):
        from reportlab.platypus import BaseDocTemplate, PageTemplate
        from reportlab.lib.units import mm

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            Report.register_fonts()
            doc = BaseDocTemplate(f.name, pagesize=self.pagesize,
                                  leftMargin=15 * mm,
                                  rightMargin=15 * mm,
                                  topMargin=20 * mm,
                                  bottomMargin=15 * mm)
            doc.addPageTemplates([
                PageTemplate(id='All', frames=self.get_frames(doc), onPage=self.on_page, pagesize=self.pagesize)
            ])
            doc.build(self.get_story(doc))
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

    def get_story(self, doc):
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

        canvas.setFont('OpenSans', 8)
        canvas.drawString(15 * mm, 10 * mm, _("Page %d") % (doc.page,))
        canvas.drawRightString(self.pagesize[0] - 15 * mm, 10 * mm,
                               _("Created: %s") % now().strftime("%d.%m.%Y %H:%M:%S"))

    def page_header(self, canvas, doc):
        from reportlab.lib.units import mm

        canvas.setFont('OpenSans', 10)
        canvas.drawString(15 * mm, self.pagesize[1] - 15 * mm,
                          "%s – %s" % (self.event.organizer.name, self.event.name))
        canvas.drawRightString(self.pagesize[0] - 15 * mm, self.pagesize[1] - 15 * mm,
                               settings.PRETIX_INSTANCE_NAME)
        canvas.setStrokeColorRGB(0, 0, 0)
        canvas.line(15 * mm, self.pagesize[1] - 17 * mm,
                    self.pagesize[0] - 15 * mm, self.pagesize[1] - 17 * mm)


class OverviewReport(Report):
    name = "overview"
    identifier = 'pdfreport'
    verbose_name = _('Order overview (PDF)')

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.landscape(pagesizes.A4)

    def get_story(self, doc):
        from reportlab.platypus import Paragraph, Spacer, TableStyle, Table
        from reportlab.lib.units import mm

        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        headlinestyle.fontName = 'OpenSansBd'
        colwidths = [
            a * doc.width for a in (.25, 0.05, .075, 0.05, .075, 0.05, .075, 0.05, .075, 0.05, .075, 0.05, .075)
        ]
        tstyledata = [
            ('SPAN', (1, 0), (2, 0)),
            ('SPAN', (3, 0), (4, 0)),
            ('SPAN', (5, 0), (6, 0)),
            ('SPAN', (7, 0), (-1, 0)),
            ('SPAN', (7, 1), (8, 1)),
            ('SPAN', (9, 1), (10, 1)),
            ('SPAN', (11, 1), (12, 1)),
            ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
            ('ALIGN', (1, 2), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 1), 'OpenSansBd'),
            ('FONTNAME', (0, -1), (-1, -1), 'OpenSansBd'),
            ('FONTSIZE', (0, 0), (-1, -1), 9)
        ]

        story = [
            Paragraph(_('Orders by product'), headlinestyle),
            Spacer(1, 5 * mm)
        ]
        tdata = [
            [
                _('Product'), _('Canceled'), '', _('Refunded'), '', _('Expired'), '', _('Purchased'),
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

        items_by_category, total = order_overview(self.event)

        for tup in items_by_category:
            if tup[0]:
                tstyledata.append(('FONTNAME', (0, len(tdata)), (-1, len(tdata)), 'OpenSansBd'))
                tdata.append([
                    tup[0].name,
                    str(tup[0].num_canceled[0]), str(tup[0].num_canceled[1]),
                    str(tup[0].num_refunded[0]), str(tup[0].num_refunded[1]),
                    str(tup[0].num_expired[0]), str(tup[0].num_expired[1]),
                    str(tup[0].num_pending[0]), str(tup[0].num_pending[1]),
                    str(tup[0].num_paid[0]), str(tup[0].num_paid[1]),
                    str(tup[0].num_total[0]), str(tup[0].num_total[1]),
                ])
            for item in tup[1]:
                tdata.append([
                    "     " + str(item.name),
                    str(item.num_canceled[0]), str(item.num_canceled[1]),
                    str(item.num_refunded[0]), str(item.num_refunded[1]),
                    str(item.num_expired[0]), str(item.num_expired[1]),
                    str(item.num_pending[0]), str(item.num_pending[1]),
                    str(item.num_paid[0]), str(item.num_paid[1]),
                    str(item.num_total[0]), str(item.num_total[1]),
                ])
                if item.has_variations:
                    for var in item.all_variations:
                        tdata.append([
                            "          " + str(var),
                            str(var.num_canceled[0]), str(var.num_canceled[1]),
                            str(var.num_refunded[0]), str(var.num_refunded[1]),
                            str(var.num_expired[0]), str(var.num_expired[1]),
                            str(var.num_pending[0]), str(var.num_pending[1]),
                            str(var.num_paid[0]), str(var.num_paid[1]),
                            str(var.num_total[0]), str(var.num_total[1]),
                        ])

        tdata.append([
            _("Total"),
            str(total['num_canceled'][0]), str(total['num_canceled'][1]),
            str(total['num_refunded'][0]), str(total['num_refunded'][1]),
            str(total['num_expired'][0]), str(total['num_expired'][1]),
            str(total['num_pending'][0]), str(total['num_pending'][1]),
            str(total['num_paid'][0]), str(total['num_paid'][1]),
            str(total['num_total'][0]), str(total['num_total'][1]),
        ])

        table = Table(tdata, colWidths=colwidths, repeatRows=3)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story


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

    def get_story(self, doc):
        from reportlab.platypus import Paragraph, Spacer, TableStyle, Table
        from reportlab.lib.units import mm

        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        headlinestyle.fontName = 'OpenSansBd'
        tz = pytz.timezone(self.event.settings.timezone)

        tax_rates = set(
            self.event.orders.exclude(payment_fee=0).values_list('payment_fee_tax_rate', flat=True)
                .filter(status__in=self.form_data['status'])
                .distinct().order_by()
        )
        tax_rates |= set(
            a for a
            in OrderPosition.objects.filter(order__event=self.event)
                                    .filter(order__status__in=self.form_data['status'])
                                    .values_list('tax_rate', flat=True).distinct().order_by()
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

        qs = OrderPosition.objects.filter(
            order__status__in=self.form_data['status'],
            order__event=self.event,
        ).values(
            'order__code', 'order__datetime', 'order__payment_date', 'order__total', 'order__payment_fee',
            'order__payment_fee_tax_rate', 'order__payment_fee_tax_value', 'tax_rate', 'order__status'
        ).annotate(prices=Sum('price'), tax_values=Sum('tax_value')).order_by(
            'order__datetime' if self.form_data['sort'] == 'datetime' else 'order__payment_date',
            'order__datetime',
            'order__code'
        )
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
                        date_format(op['order__payment_date'], "SHORT_DATE_FORMAT") if op['order__payment_date'] else '',
                        str(op['order__total'])
                    ] + sum((['', ''] for t in tax_rates), []),
                )
                last_order_code = op['order__code']
                if op['order__payment_fee_tax_value']:
                    tdata[-1][5 + 2 * tax_rates.index(op['order__payment_fee_tax_rate'])] = str(op['order__payment_fee'])
                    tdata[-1][6 + 2 * tax_rates.index(op['order__payment_fee_tax_rate'])] = str(op['order__payment_fee_tax_value'])
                    tax_sums[op['order__payment_fee_tax_rate']] += op['order__payment_fee_tax_value']
                    price_sums[op['order__payment_fee_tax_rate']] += op['order__payment_fee']

                i = tax_rates.index(op['tax_rate'])
                tdata[-1][5 + 2 * i] = str(Decimal(tdata[-1][5 + 2 * i] or '0') + op['prices'])
                tdata[-1][6 + 2 * i] = str(Decimal(tdata[-1][6 + 2 * i] or '0') + op['tax_values'])
                tax_sums[op['tax_rate']] += op['tax_values']
                price_sums[op['tax_rate']] += op['prices']

        tdata.append(
            [
                _('Total'), '', '', '', ''
            ] + sum(([str(price_sums.get(t)), str(tax_sums.get(t))] for t in tax_rates), []),
        )

        table = Table(tdata, colWidths=colwidths, repeatRows=2)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story
