import copy
import tempfile
from collections import defaultdict
from datetime import date
from decimal import Decimal
from locale import format as lformat

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import pgettext, ugettext as _
from reportlab.lib import pagesizes
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

from pretix.base.models import Invoice, InvoiceAddress, InvoiceLine, Order
from pretix.base.signals import register_payment_providers


def generate_cancellation(invoice: Invoice):
    cancellation = copy.copy(invoice)
    cancellation.pk = None
    cancellation.is_cancellation = True
    cancellation.date = date.today()
    cancellation.refers = invoice
    cancellation.invoice_no = None
    cancellation.save()
    for line in invoice.lines.all():
        line.pk = None
        line.invoice = cancellation
        line.gross_value *= -1
        line.tax_value *= -1
        line.save()

    invoice_pdf(cancellation.pk)


@transaction.atomic
def generate_invoice(order: Order):
    locale = order.event.settings.get('invoice_language')
    _lng = translation.get_language()
    if locale:
        if locale == '__user__':
            locale = order.locale
        translation.activate(locale or settings.LANGUAGE_CODE)

    i = Invoice(order=order, event=order.event)
    i.invoice_from = order.event.settings.get('invoice_address_from')
    i.additional_text = order.event.settings.get('invoice_additional_text')

    try:
        addr_template = pgettext("invoice", """{i.company}
{i.name}
{i.street}
{i.zipcode} {i.city}
{i.country}""")
        i.invoice_to = addr_template.format(i=order.invoice_address).strip()
        if order.invoice_address.vat_id:
            i.invoice_to += "\n" + pgettext("invoice", "VAT-ID: %s") % {i.vat_id}
    except InvoiceAddress.DoesNotExist:
        i.invoice_to = ""

    i.date = date.today()
    i.locale = locale
    i.save()

    responses = register_payment_providers.send(order.event)
    for receiver, response in responses:
        provider = response(order.event)
        if provider.identifier == order.payment_provider:
            payment_provider = provider
            break

    for p in order.positions.all():
        desc = str(p.item.name)
        if p.variation:
            desc += " - " + str(p.variation.value)
        InvoiceLine.objects.create(
            invoice=i, description=desc,
            gross_value=p.price, tax_value=p.tax_value,
            tax_rate=p.tax_rate
        )

    if order.payment_fee:
        InvoiceLine.objects.create(
            invoice=i, description=_('Payment via {method}').format(method=str(payment_provider.verbose_name)),
            gross_value=order.payment_fee, tax_value=order.payment_fee_tax_value,
            tax_rate=order.payment_fee_tax_rate
        )

    translation.activate(_lng)
    invoice_pdf(i.pk)


def _invoice_get_stylesheet():
    stylesheet = StyleSheet1()
    stylesheet.add(ParagraphStyle(name='Normal', fontName='OpenSans', fontSize=10, leading=12))
    stylesheet.add(ParagraphStyle(name='Heading1', fontName='OpenSansBd', fontSize=15, leading=15 * 1.2))
    return stylesheet


def _invoice_register_fonts():
    pdfmetrics.registerFont(TTFont('OpenSans', finders.find('fonts/OpenSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('OpenSansIt', finders.find('fonts/OpenSans-Italic.ttf')))
    pdfmetrics.registerFont(TTFont('OpenSansBd', finders.find('fonts/OpenSans-Bold.ttf')))


def _invoice_generate_german(invoice, f):
    _invoice_register_fonts()
    styles = _invoice_get_stylesheet()
    pagesize = pagesizes.A4

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont('OpenSans', 8)
        canvas.drawRightString(pagesize[0] - 20 * mm, 10 * mm, _("Page %d") % (doc.page,))
        canvas.restoreState()

    def on_first_page(canvas, doc):
        canvas.setCreator('pretix.eu')
        canvas.setTitle(pgettext('invoice', 'Invoice {num}').format(num=invoice.number))

        canvas.saveState()
        canvas.setFont('OpenSans', 8)
        canvas.drawRightString(pagesize[0] - 20 * mm, 10 * mm, _("Page %d") % (doc.page,))

        textobject = canvas.beginText(25 * mm, (297 - 15) * mm)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(pgettext('invoice', 'Invoice from').upper())
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSans', 10)
        textobject.textLines(invoice.invoice_from.strip())
        canvas.drawText(textobject)

        textobject = canvas.beginText(25 * mm, (297 - 50) * mm)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(pgettext('invoice', 'Invoice to').upper())
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSans', 10)
        textobject.textLines(invoice.invoice_to.strip())
        canvas.drawText(textobject)

        textobject = canvas.beginText(125 * mm, (297 - 50) * mm)
        textobject.setFont('OpenSansBd', 8)
        if invoice.is_cancellation:
            textobject.textLine(pgettext('invoice', 'Cancellation number').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSans', 10)
            textobject.textLine(invoice.number)
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSansBd', 8)
            textobject.textLine(pgettext('invoice', 'Original invoice').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSans', 10)
            textobject.textLine(invoice.refers.number)
        else:
            textobject.textLine(pgettext('invoice', 'Invoice number').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSans', 10)
            textobject.textLine(invoice.number)
        textobject.moveCursor(0, 5)

        if invoice.is_cancellation:
            textobject.setFont('OpenSansBd', 8)
            textobject.textLine(pgettext('invoice', 'Cancellation date').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSans', 10)
            textobject.textLine(date_format(invoice.date, "DATE_FORMAT"))
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSansBd', 8)
            textobject.textLine(pgettext('invoice', 'Original invoice date').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSans', 10)
            textobject.textLine(date_format(invoice.refers.date, "DATE_FORMAT"))
            textobject.moveCursor(0, 5)
        else:
            textobject.setFont('OpenSansBd', 8)
            textobject.textLine(pgettext('invoice', 'Invoice date').upper())
            textobject.moveCursor(0, 5)
            textobject.setFont('OpenSans', 10)
            textobject.textLine(date_format(invoice.date, "DATE_FORMAT"))
            textobject.moveCursor(0, 5)

        canvas.drawText(textobject)

        textobject = canvas.beginText(165 * mm, (297 - 50) * mm)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(_('Order code').upper())
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSans', 10)
        textobject.textLine(invoice.order.code)
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(_('Order date').upper())
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSans', 10)
        textobject.textLine(date_format(invoice.order.datetime, "DATE_FORMAT"))
        canvas.drawText(textobject)

        textobject = canvas.beginText(125 * mm, (297 - 15) * mm)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(_('Event').upper())
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSans', 10)
        textobject.textLine(str(invoice.event.name))
        if invoice.event.settings.show_date_to:
            textobject.textLines(
                _('%s\nuntil %s') % (invoice.event.get_date_from_display(),
                                     invoice.event.get_date_to_display()))
        else:
            textobject.textLine(invoice.event.get_date_from_display())
        canvas.drawText(textobject)

        canvas.restoreState()

    doc = BaseDocTemplate(f.name, pagesize=pagesizes.A4,
                          leftMargin=25 * mm, rightMargin=20 * mm,
                          topMargin=20 * mm, bottomMargin=15 * mm)
    frames_p1 = [
        Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - 75 * mm,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
              id='normal')
    ]
    frames = [
        Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
              id='normal')
    ]
    doc.addPageTemplates([
        PageTemplate(id='FirstPage', frames=frames_p1, onPage=on_first_page, pagesize=pagesize),
        PageTemplate(id='OtherPages', frames=frames, onPage=on_page, pagesize=pagesize)
    ])
    story = [
        NextPageTemplate('FirstPage'),
        Paragraph(pgettext('invoice', 'Invoice')
                  if not invoice.is_cancellation
                  else pgettext('invoice', 'Cancellation'),
                  styles['Heading1']),
        Spacer(1, 5 * mm),
        NextPageTemplate('OtherPages'),
    ]

    taxvalue_map = defaultdict(Decimal)
    grossvalue_map = defaultdict(Decimal)

    tstyledata = [
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'OpenSansBd'),
        ('FONTNAME', (0, -1), (-1, -1), 'OpenSansBd'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]
    tdata = [(pgettext('invoice', 'Description'), pgettext('invoice', 'Tax rate'), pgettext('invoice', 'Price'))]
    total = Decimal('0.00')
    for line in invoice.lines.all():
        tdata.append((
            line.description,
            lformat("%.2f", line.tax_rate) + " %",
            lformat("%.2f", line.gross_value) + " " + invoice.event.currency,
        ))
        taxvalue_map[line.tax_rate] += line.tax_value
        grossvalue_map[line.tax_rate] += line.gross_value
        total += line.gross_value

    tdata.append([pgettext('invoice', 'Invoice total'), '', lformat("%.2f", total) + " " + invoice.event.currency])
    colwidths = [a * doc.width for a in (.60, .20, .20)]
    table = Table(tdata, colWidths=colwidths, repeatRows=1)
    table.setStyle(TableStyle(tstyledata))
    story.append(table)

    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph(invoice.additional_text, styles['Normal']))
    story.append(Spacer(1, 15 * mm))

    tstyledata = [
        ('SPAN', (1, 0), (-1, 0)),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]
    tdata = [('', pgettext('invoice', 'Included taxes'), '', '', ''),
             ('', pgettext('invoice', 'Tax rate'),
              pgettext('invoice', 'Net value'), pgettext('invoice', 'Gross value'), pgettext('invoice', 'Tax'))]

    for rate, gross in grossvalue_map.items():
        if line.tax_rate == 0:
            continue
        tax = taxvalue_map[rate]
        tdata.append((
            '',
            lformat("%.2f", rate) + " %",
            lformat("%.2f", (gross - tax)) + " " + invoice.event.currency,
            lformat("%.2f", gross) + " " + invoice.event.currency,
            lformat("%.2f", tax) + " " + invoice.event.currency,
        ))

    if len(tdata) > 2:
        colwidths = [a * doc.width for a in (.45, .10, .15, .15, .15)]
        table = Table(tdata, colWidths=colwidths, repeatRows=2)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)

    doc.build(story)
    return doc


def invoice_pdf(invoice: int):
    i = Invoice.objects.get(pk=invoice)
    _lng = translation.get_language()
    translation.activate(i.locale)

    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        _invoice_generate_german(i, f)
        f.seek(0)
        i.file.save('invoice.pdf', ContentFile(f.read()))
    i.save()

    translation.activate(_lng)
    return i.file.name


if settings.HAS_CELERY:
    from pretix.celery import app

    invoice_pdf_task = app.task(invoice_pdf)

    def invoice_pdf(*args, **kwargs):
        invoice_pdf_task.apply_async(args=args, kwargs=kwargs)
