import logging
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from typing import Tuple

import bleach
import vat_moss.exchange_rates
from django.contrib.staticfiles import finders
from django.dispatch import receiver
from django.utils.formats import date_format, localize
from django.utils.translation import pgettext
from PIL.Image import BICUBIC
from reportlab.lib import pagesizes
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

from pretix.base.decimal import round_decimal
from pretix.base.models import Event, Invoice
from pretix.base.signals import register_invoice_renderers
from pretix.base.templatetags.money import money_filter

logger = logging.getLogger(__name__)


class NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        self.font_regular = kwargs.pop('font_regular')
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            Canvas.showPage(self)
        Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont(self.font_regular, 8)
        self.drawRightString(self._pagesize[0] - 20 * mm, 10 * mm, pgettext("invoice", "Page %d of %d") % (self._pageNumber, page_count,))
        self.restoreState()


class BaseInvoiceRenderer:
    """
    This is the base class for all invoice renderers.
    """

    def __init__(self, event: Event):
        self.event = event

    def __str__(self):
        return self.identifier

    def generate(self, invoice: Invoice) -> Tuple[str, str, str]:
        """
        This method should generate the invoice file and return a tuple consisting of a
        filename, a file type and file content. The extension will be taken from the filename
        which is otherwise ignored.
        """
        raise NotImplementedError()

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this renderer. This should be short but
        self-explanatory. Good examples include 'German DIN 5008' or 'Italian invoice'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this renderer.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA


class BaseReportlabInvoiceRenderer(BaseInvoiceRenderer):
    """
    This is a convenience class to avoid duplicate code when implementing invoice renderers
    that are based on reportlab.
    """
    pagesize = pagesizes.A4
    left_margin = 25 * mm
    right_margin = 20 * mm
    top_margin = 20 * mm
    bottom_margin = 15 * mm
    doc_template_class = BaseDocTemplate
    canvas_class = Canvas
    font_regular = 'OpenSans'
    font_bold = 'OpenSansBd'

    def _init(self):
        """
        Initialize the renderer. By default, this registers fonts and sets ``self.stylesheet``.
        """
        self.stylesheet = self._get_stylesheet()
        self._register_fonts()

    def _get_stylesheet(self):
        """
        Get a stylesheet. By default, this contains the "Normal" and "Heading1" styles.
        """
        stylesheet = StyleSheet1()
        stylesheet.add(ParagraphStyle(name='Normal', fontName=self.font_regular, fontSize=10, leading=12))
        stylesheet.add(ParagraphStyle(name='Heading1', fontName=self.font_bold, fontSize=15, leading=15 * 1.2))
        stylesheet.add(ParagraphStyle(name='FineprintHeading', fontName=self.font_bold, fontSize=8, leading=12))
        stylesheet.add(ParagraphStyle(name='Fineprint', fontName=self.font_regular, fontSize=8, leading=10))
        return stylesheet

    def _register_fonts(self):
        """
        Register fonts with reportlab. By default, this registers the OpenSans font family
        """
        pdfmetrics.registerFont(TTFont('OpenSans', finders.find('fonts/OpenSans-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('OpenSansIt', finders.find('fonts/OpenSans-Italic.ttf')))
        pdfmetrics.registerFont(TTFont('OpenSansBd', finders.find('fonts/OpenSans-Bold.ttf')))
        pdfmetrics.registerFont(TTFont('OpenSansBI', finders.find('fonts/OpenSans-BoldItalic.ttf')))
        pdfmetrics.registerFontFamily('OpenSans', normal='OpenSans', bold='OpenSansBd',
                                      italic='OpenSansIt', boldItalic='OpenSansBI')

    def _on_other_page(self, canvas: Canvas, doc):
        """
        Called when a new page is rendered that is *not* the first page.
        """
        pass

    def _on_first_page(self, canvas: Canvas, doc):
        """
        Called when a new page is rendered that is the first page.
        """
        pass

    def _get_story(self, doc):
        """
        Called to create the story to be inserted into the main frames.
        """
        raise NotImplementedError()

    def _get_first_page_frames(self, doc):
        """
        Called to create a list of frames for the first page.
        """
        return [
            Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - 75 * mm,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                  id='normal')
        ]

    def _get_other_page_frames(self, doc):
        """
        Called to create a list of frames for the other pages.
        """
        return [
            Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                  id='normal')
        ]

    def _build_doc(self, fhandle):
        """
        Build a PDF document in a given file handle
        """
        self._init()
        doc = self.doc_template_class(fhandle, pagesize=self.pagesize,
                                      leftMargin=self.left_margin, rightMargin=self.right_margin,
                                      topMargin=self.top_margin, bottomMargin=self.bottom_margin)

        doc.addPageTemplates([
            PageTemplate(
                id='FirstPage',
                frames=self._get_first_page_frames(doc),
                onPage=self._on_first_page,
                pagesize=self.pagesize
            ),
            PageTemplate(
                id='OtherPages',
                frames=self._get_other_page_frames(doc),
                onPage=self._on_other_page,
                pagesize=self.pagesize
            )
        ])
        story = self._get_story(doc)
        doc.build(story, canvasmaker=self.canvas_class)
        return doc

    def generate(self, invoice: Invoice):
        self.invoice = invoice
        buffer = BytesIO()
        self._build_doc(buffer)
        buffer.seek(0)
        return 'invoice.pdf', 'application/pdf', buffer.read()


class ThumbnailingImageReader(ImageReader):
    def resize(self, width, height, dpi):
        if width is None:
            width = height * self._image.size[0] / self._image.size[1]
        if height is None:
            height = width * self._image.size[1] / self._image.size[0]
        self._image.thumbnail(
            size=(int(width * dpi / 72), int(height * dpi / 72)),
            resample=BICUBIC
        )
        self._data = None
        return width, height

    def _jpeg_fh(self):
        # Bypass a reportlab-internal optimization that falls back to the original
        # file handle if the file is a JPEG, and therefore does not respect the
        # (smaller) size of the modified image.
        return None


class ClassicInvoiceRenderer(BaseReportlabInvoiceRenderer):
    identifier = 'classic'
    verbose_name = pgettext('invoice', 'Classic renderer (pretix 1.0)')

    def canvas_class(self, *args, **kwargs):
        kwargs['font_regular'] = self.font_regular
        return NumberedCanvas(*args, **kwargs)

    def _on_other_page(self, canvas: Canvas, doc):
        canvas.saveState()
        canvas.setFont(self.font_regular, 8)

        for i, line in enumerate(self.invoice.footer_text.split('\n')[::-1]):
            canvas.drawCentredString(self.pagesize[0] / 2, 25 + (3.5 * i) * mm, line.strip())

        canvas.restoreState()

    def _draw_invoice_to(self, canvas):
        p = Paragraph(self.invoice.invoice_to.strip().replace('\n', '<br />\n'), style=self.stylesheet['Normal'])
        p.wrapOn(canvas, 85 * mm, 50 * mm)
        p_size = p.wrap(85 * mm, 50 * mm)
        p.drawOn(canvas, 25 * mm, (297 - 52) * mm - p_size[1])

    def _draw_invoice_from(self, canvas):
        p = Paragraph(self.invoice.full_invoice_from.strip().replace('\n', '<br />\n'), style=self.stylesheet['Normal'])
        p.wrapOn(canvas, 70 * mm, 50 * mm)
        p_size = p.wrap(70 * mm, 50 * mm)
        p.drawOn(canvas, 25 * mm, (297 - 17) * mm - p_size[1])

    def _on_first_page(self, canvas: Canvas, doc):
        canvas.setCreator('pretix.eu')
        canvas.setTitle(pgettext('invoice', 'Invoice {num}').format(num=self.invoice.number))

        canvas.saveState()
        canvas.setFont(self.font_regular, 8)

        for i, line in enumerate(self.invoice.footer_text.split('\n')[::-1]):
            canvas.drawCentredString(self.pagesize[0] / 2, 25 + (3.5 * i) * mm, line.strip())

        textobject = canvas.beginText(25 * mm, (297 - 15) * mm)
        textobject.setFont(self.font_bold, 8)
        textobject.textLine(pgettext('invoice', 'Invoice from').upper())
        canvas.drawText(textobject)

        self._draw_invoice_from(canvas)

        textobject = canvas.beginText(25 * mm, (297 - 50) * mm)
        textobject.setFont(self.font_bold, 8)
        textobject.textLine(pgettext('invoice', 'Invoice to').upper())
        canvas.drawText(textobject)

        self._draw_invoice_to(canvas)

        textobject = canvas.beginText(125 * mm, (297 - 38) * mm)
        textobject.setFont(self.font_bold, 8)
        textobject.textLine(pgettext('invoice', 'Order code').upper())
        textobject.moveCursor(0, 5)
        textobject.setFont(self.font_regular, 10)
        textobject.textLine(self.invoice.order.full_code)
        canvas.drawText(textobject)

        textobject = canvas.beginText(125 * mm, (297 - 50) * mm)
        textobject.setFont(self.font_bold, 8)
        if self.invoice.is_cancellation:
            textobject.textLine(pgettext('invoice', 'Cancellation number').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_regular, 10)
            textobject.textLine(self.invoice.number)
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_bold, 8)
            textobject.textLine(pgettext('invoice', 'Original invoice').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_regular, 10)
            textobject.textLine(self.invoice.refers.number)
        else:
            textobject.textLine(pgettext('invoice', 'Invoice number').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_regular, 10)
            textobject.textLine(self.invoice.number)
        textobject.moveCursor(0, 5)

        if self.invoice.is_cancellation:
            textobject.setFont(self.font_bold, 8)
            textobject.textLine(pgettext('invoice', 'Cancellation date').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_regular, 10)
            textobject.textLine(date_format(self.invoice.date, "DATE_FORMAT"))
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_bold, 8)
            textobject.textLine(pgettext('invoice', 'Original invoice date').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_regular, 10)
            textobject.textLine(date_format(self.invoice.refers.date, "DATE_FORMAT"))
            textobject.moveCursor(0, 5)
        else:
            textobject.setFont(self.font_bold, 8)
            textobject.textLine(pgettext('invoice', 'Invoice date').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont(self.font_regular, 10)
            textobject.textLine(date_format(self.invoice.date, "DATE_FORMAT"))
            textobject.moveCursor(0, 5)

        canvas.drawText(textobject)

        if self.invoice.event.settings.invoice_logo_image:
            logo_file = self.invoice.event.settings.get('invoice_logo_image', binary_file=True)
            ir = ThumbnailingImageReader(logo_file)
            try:
                ir.resize(25 * mm, 25 * mm, 300)
            except:
                logger.exception("Can not resize image")
                pass
            canvas.drawImage(ir,
                             95 * mm, (297 - 38) * mm,
                             width=25 * mm, height=25 * mm,
                             preserveAspectRatio=True, anchor='n',
                             mask='auto')

        def shorten(txt):
            txt = str(txt)
            p = Paragraph(txt.strip().replace('\n', '<br />\n'), style=self.stylesheet['Normal'])
            p_size = p.wrap(65 * mm, 50 * mm)

            while p_size[1] > 2 * self.stylesheet['Normal'].leading:
                txt = ' '.join(txt.replace('…', '').split()[:-1]) + '…'
                p = Paragraph(txt.strip().replace('\n', '<br />\n'), style=self.stylesheet['Normal'])
                p_size = p.wrap(65 * mm, 50 * mm)
            return txt

        if not self.invoice.event.has_subevents:
            if self.invoice.event.settings.show_date_to and self.invoice.event.date_to:
                p_str = (
                    shorten(self.invoice.event.name) + '\n' + pgettext('invoice', '{from_date}\nuntil {to_date}').format(
                        from_date=self.invoice.event.get_date_from_display(),
                        to_date=self.invoice.event.get_date_to_display())
                )
            else:
                p_str = (
                    shorten(self.invoice.event.name) + '\n' + self.invoice.event.get_date_from_display()
                )
        else:
            p_str = shorten(self.invoice.event.name)

        p = Paragraph(p_str.strip().replace('\n', '<br />\n'), style=self.stylesheet['Normal'])
        p.wrapOn(canvas, 65 * mm, 50 * mm)
        p_size = p.wrap(65 * mm, 50 * mm)
        p.drawOn(canvas, 125 * mm, (297 - 17) * mm - p_size[1])

        textobject = canvas.beginText(125 * mm, (297 - 15) * mm)
        textobject.setFont(self.font_bold, 8)
        textobject.textLine(pgettext('invoice', 'Event').upper())
        canvas.drawText(textobject)

        canvas.restoreState()

    def _get_first_page_frames(self, doc):
        footer_length = 3.5 * len(self.invoice.footer_text.split('\n')) * mm
        return [
            Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - 75 * mm,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=footer_length,
                  id='normal')
        ]

    def _get_other_page_frames(self, doc):
        footer_length = 3.5 * len(self.invoice.footer_text.split('\n')) * mm
        return [
            Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=footer_length,
                  id='normal')
        ]

    def _get_story(self, doc):
        has_taxes = any(il.tax_value for il in self.invoice.lines.all())

        story = [
            NextPageTemplate('FirstPage'),
            Paragraph(pgettext('invoice', 'Invoice')
                      if not self.invoice.is_cancellation
                      else pgettext('invoice', 'Cancellation'),
                      self.stylesheet['Heading1']),
            Spacer(1, 5 * mm),
            NextPageTemplate('OtherPages'),
        ]

        if self.invoice.internal_reference:
            story.append(Paragraph(
                pgettext('invoice', 'Customer reference: {reference}').format(reference=self.invoice.internal_reference),
                self.stylesheet['Normal']
            ))

        if self.invoice.invoice_to_beneficiary:
            story.append(Paragraph(
                pgettext('invoice', 'Beneficiary') + ':<br />' +
                bleach.clean(self.invoice.invoice_to_beneficiary, tags=[]).replace("\n", "<br />\n"),
                self.stylesheet['Normal']
            ))

        if self.invoice.introductory_text:
            story.append(Paragraph(self.invoice.introductory_text, self.stylesheet['Normal']))
            story.append(Spacer(1, 10 * mm))

        taxvalue_map = defaultdict(Decimal)
        grossvalue_map = defaultdict(Decimal)

        tstyledata = [
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), self.font_bold),
            ('FONTNAME', (0, -1), (-1, -1), self.font_bold),
            ('LEFTPADDING', (0, 0), (0, -1), 0),
            ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
        ]
        if has_taxes:
            tdata = [(
                pgettext('invoice', 'Description'),
                pgettext('invoice', 'Qty'),
                pgettext('invoice', 'Tax rate'),
                pgettext('invoice', 'Net'),
                pgettext('invoice', 'Gross'),
            )]
        else:
            tdata = [(
                pgettext('invoice', 'Description'),
                pgettext('invoice', 'Qty'),
                pgettext('invoice', 'Amount'),
            )]

        total = Decimal('0.00')
        for line in self.invoice.lines.all():
            if has_taxes:
                tdata.append((
                    Paragraph(line.description, self.stylesheet['Normal']),
                    "1",
                    localize(line.tax_rate) + " %",
                    money_filter(line.net_value, self.invoice.event.currency),
                    money_filter(line.gross_value, self.invoice.event.currency),
                ))
            else:
                tdata.append((
                    Paragraph(line.description, self.stylesheet['Normal']),
                    "1",
                    money_filter(line.gross_value, self.invoice.event.currency),
                ))
            taxvalue_map[line.tax_rate, line.tax_name] += line.tax_value
            grossvalue_map[line.tax_rate, line.tax_name] += line.gross_value
            total += line.gross_value

        if has_taxes:
            tdata.append([
                pgettext('invoice', 'Invoice total'), '', '', '', money_filter(total, self.invoice.event.currency)
            ])
            colwidths = [a * doc.width for a in (.50, .05, .15, .15, .15)]
        else:
            tdata.append([
                pgettext('invoice', 'Invoice total'), '', money_filter(total, self.invoice.event.currency)
            ])
            colwidths = [a * doc.width for a in (.65, .05, .30)]

        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)

        story.append(Spacer(1, 15 * mm))

        if self.invoice.payment_provider_text:
            story.append(Paragraph(self.invoice.payment_provider_text, self.stylesheet['Normal']))

        if self.invoice.additional_text:
            story.append(Paragraph(self.invoice.additional_text, self.stylesheet['Normal']))
            story.append(Spacer(1, 15 * mm))

        tstyledata = [
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (0, -1), 0),
            ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, -1), self.font_regular),
        ]
        thead = [
            pgettext('invoice', 'Tax rate'),
            pgettext('invoice', 'Net value'),
            pgettext('invoice', 'Gross value'),
            pgettext('invoice', 'Tax'),
            ''
        ]
        tdata = [thead]

        for idx, gross in grossvalue_map.items():
            rate, name = idx
            if rate == 0:
                continue
            tax = taxvalue_map[idx]
            tdata.append([
                localize(rate) + " % " + name,
                money_filter(gross - tax, self.invoice.event.currency),
                money_filter(gross, self.invoice.event.currency),
                money_filter(tax, self.invoice.event.currency),
                ''
            ])

        def fmt(val):
            try:
                return vat_moss.exchange_rates.format(val, self.invoice.foreign_currency_display)
            except ValueError:
                return localize(val) + ' ' + self.invoice.foreign_currency_display

        if len(tdata) > 1 and has_taxes:
            colwidths = [a * doc.width for a in (.25, .15, .15, .15, .3)]
            table = Table(tdata, colWidths=colwidths, repeatRows=2, hAlign=TA_LEFT)
            table.setStyle(TableStyle(tstyledata))
            story.append(KeepTogether([
                Paragraph(pgettext('invoice', 'Included taxes'), self.stylesheet['FineprintHeading']),
                table
            ]))

            if self.invoice.foreign_currency_display and self.invoice.foreign_currency_rate:
                tdata = [thead]

                for idx, gross in grossvalue_map.items():
                    rate, name = idx
                    if rate == 0:
                        continue
                    tax = taxvalue_map[idx]
                    gross = round_decimal(gross * self.invoice.foreign_currency_rate)
                    tax = round_decimal(tax * self.invoice.foreign_currency_rate)
                    net = gross - tax

                    tdata.append([
                        localize(rate) + " % " + name,
                        fmt(net), fmt(gross), fmt(tax), ''
                    ])

                table = Table(tdata, colWidths=colwidths, repeatRows=2, hAlign=TA_LEFT)
                table.setStyle(TableStyle(tstyledata))

                story.append(KeepTogether([
                    Spacer(1, height=2 * mm),
                    Paragraph(
                        pgettext(
                            'invoice', 'Using the conversion rate of 1:{rate} as published by the European Central Bank on '
                                       '{date}, this corresponds to:'
                        ).format(rate=localize(self.invoice.foreign_currency_rate),
                                 date=date_format(self.invoice.foreign_currency_rate_date, "SHORT_DATE_FORMAT")),
                        self.stylesheet['Fineprint']
                    ),
                    Spacer(1, height=3 * mm),
                    table
                ]))
        elif self.invoice.foreign_currency_display and self.invoice.foreign_currency_rate:
            story.append(Spacer(1, 5 * mm))
            story.append(Paragraph(
                pgettext(
                    'invoice', 'Using the conversion rate of 1:{rate} as published by the European Central Bank on '
                               '{date}, the invoice total corresponds to {total}.'
                ).format(rate=localize(self.invoice.foreign_currency_rate),
                         date=date_format(self.invoice.foreign_currency_rate_date, "SHORT_DATE_FORMAT"),
                         total=fmt(total)),
                self.stylesheet['Fineprint']
            ))

        return story


@receiver(register_invoice_renderers, dispatch_uid="invoice_renderer_classic")
def recv_classic(sender, **kwargs):
    return ClassicInvoiceRenderer
