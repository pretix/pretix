import tempfile

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.exporter import BaseExporter
from pretix.base.services.stats import order_overview


class Report:
    name = "report"

    def __init__(self, event):
        self.event = event

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.portrait(pagesizes.A4)

    def get_filename(self):
        return "%s-%s.pdf" % (self.name, now().strftime("%Y-%m-%d-%H-%M-%S"))

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
        colwidths = [a * doc.width for a in (.30, .06, .08, .06, .08, .06, .08, .06, .08, .06, .08)]
        tstyledata = [
            ('SPAN', (1, 0), (2, 0)),
            ('SPAN', (3, 0), (4, 0)),
            ('SPAN', (5, 0), (6, 0)),
            ('SPAN', (7, 0), (8, 0)),
            ('SPAN', (9, 0), (10, 0)),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'OpenSansBd'),
            ('FONTNAME', (0, -1), (-1, -1), 'OpenSansBd'),
        ]

        story = [
            Paragraph(_('Orders by product'), headlinestyle),
            Spacer(1, 5 * mm)
        ]
        tdata = [
            [
                _('Product'), _('Total orders'), '', _('Pending'), '', _('Cancelled'), '', _('Refunded'), '',
                _('Paid'), ''
            ],
            [
                '',
                _('Number'), self.event.currency,
                _('Number'), self.event.currency,
                _('Number'), self.event.currency,
                _('Number'), self.event.currency,
                _('Number'), self.event.currency
            ],
        ]

        items_by_category, total = order_overview(self.event)

        for tup in items_by_category:
            if tup[0]:
                tstyledata.append(('FONTNAME', (0, len(tdata)), (-1, len(tdata)), 'OpenSansBd'))
                tdata.append([
                    tup[0].name,
                    str(tup[0].num_total[0]), str(tup[0].num_total[1]),
                    str(tup[0].num_pending[0]), str(tup[0].num_pending[1]),
                    str(tup[0].num_cancelled[0]), str(tup[0].num_cancelled[1]),
                    str(tup[0].num_refunded[0]), str(tup[0].num_refunded[1]),
                    str(tup[0].num_paid[0]), str(tup[0].num_paid[1])
                ])
            for item in tup[1]:
                tdata.append([
                    "     " + str(item.name),
                    str(item.num_total[0]), str(item.num_total[1]),
                    str(item.num_pending[0]), str(item.num_pending[1]),
                    str(item.num_cancelled[0]), str(item.num_cancelled[1]),
                    str(item.num_refunded[0]), str(item.num_refunded[1]),
                    str(item.num_paid[0]), str(item.num_paid[1])
                ])
                if item.has_variations:
                    for var in item.all_variations:
                        tdata.append([
                            "          " + str(var),
                            str(var.num_total[0]), str(var.num_total[1]),
                            str(var.num_pending[0]), str(var.num_pending[1]),
                            str(var.num_cancelled[0]), str(var.num_cancelled[1]),
                            str(var.num_refunded[0]), str(var.num_refunded[1]),
                            str(var.num_paid[0]), str(var.num_paid[1])
                        ])

        tdata.append([
            _("Total"),
            str(total['num_total'][0]), str(total['num_total'][1]),
            str(total['num_pending'][0]), str(total['num_pending'][1]),
            str(total['num_cancelled'][0]), str(total['num_cancelled'][1]),
            str(total['num_refunded'][0]), str(total['num_refunded'][1]),
            str(total['num_paid'][0]), str(total['num_paid'][1])
        ])

        table = Table(tdata, colWidths=colwidths, repeatRows=2)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story


class OverviewReportExporter(BaseExporter):
    identifier = 'pdfreport'
    verbose_name = _('Order overview (PDF)')

    def render(self, form_data):
        report = OverviewReport(self.event)
        return 'report-%s.pdf' % self.event.slug, 'application/pdf', report.create()
