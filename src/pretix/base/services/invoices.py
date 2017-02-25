import copy
import tempfile
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.formats import date_format, localize
from django.utils.timezone import now
from django.utils.translation import pgettext, ugettext as _
from i18nfield.strings import LazyI18nString
from reportlab.lib import pagesizes
from reportlab.lib.styles import ParagraphStyle, StyleSheet1
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

from pretix.base.i18n import language
from pretix.base.models import Invoice, InvoiceAddress, InvoiceLine, Order
from pretix.base.services.async import TransactionAwareTask
from pretix.base.signals import register_payment_providers
from pretix.celery_app import app
from pretix.helpers.database import rolledback_transaction


@transaction.atomic
def build_invoice(invoice: Invoice) -> Invoice:
    with language(invoice.locale):
        responses = register_payment_providers.send(invoice.event)
        for receiver, response in responses:
            provider = response(invoice.event)
            if provider.identifier == invoice.order.payment_provider:
                payment_provider = provider
                break

        invoice.invoice_from = invoice.event.settings.get('invoice_address_from')

        introductory = invoice.event.settings.get('invoice_introductory_text', as_type=LazyI18nString)
        additional = invoice.event.settings.get('invoice_additional_text', as_type=LazyI18nString)
        footer = invoice.event.settings.get('invoice_footer_text', as_type=LazyI18nString)
        payment = payment_provider.render_invoice_text(invoice.order)

        invoice.introductory_text = str(introductory).replace('\n', '<br />')
        invoice.additional_text = str(additional).replace('\n', '<br />')
        invoice.footer_text = str(footer)
        invoice.payment_provider_text = str(payment).replace('\n', '<br />')

        try:
            addr_template = pgettext("invoice", """{i.company}
{i.name}
{i.street}
{i.zipcode} {i.city}
{i.country}""")
            invoice.invoice_to = addr_template.format(i=invoice.order.invoice_address).strip()
            if invoice.order.invoice_address.vat_id:
                invoice.invoice_to += "\n" + pgettext("invoice", "VAT-ID: %s") % invoice.order.invoice_address.vat_id
        except InvoiceAddress.DoesNotExist:
            invoice.invoice_to = ""

        invoice.file = None
        invoice.save()
        invoice.lines.all().delete()

        for p in invoice.order.positions.all():
            desc = str(p.item.name)
            if p.variation:
                desc += " - " + str(p.variation.value)
            InvoiceLine.objects.create(
                invoice=invoice, description=desc,
                gross_value=p.price, tax_value=p.tax_value,
                tax_rate=p.tax_rate
            )

        if invoice.order.payment_fee:
            InvoiceLine.objects.create(
                invoice=invoice, description=_('Payment via {method}').format(method=str(payment_provider.verbose_name)),
                gross_value=invoice.order.payment_fee, tax_value=invoice.order.payment_fee_tax_value,
                tax_rate=invoice.order.payment_fee_tax_rate
            )

        return invoice


def build_cancellation(invoice: Invoice):
    invoice.lines.all().delete()

    for line in invoice.refers.lines.all():
        line.pk = None
        line.invoice = invoice
        line.gross_value *= -1
        line.tax_value *= -1
        line.save()
    return invoice


def generate_cancellation(invoice: Invoice):
    cancellation = copy.copy(invoice)
    cancellation.pk = None
    cancellation.invoice_no = None
    cancellation.refers = invoice
    cancellation.is_cancellation = True
    cancellation.date = date.today()
    cancellation.payment_provider_text = ''
    cancellation.save()

    cancellation = build_cancellation(cancellation)
    invoice_pdf(cancellation.pk)
    return cancellation


def regenerate_invoice(invoice: Invoice):
    if invoice.is_cancellation:
        invoice = build_cancellation(invoice)
    else:
        invoice = build_invoice(invoice)
    invoice_pdf(invoice.pk)
    return invoice


def generate_invoice(order: Order):
    locale = order.event.settings.get('invoice_language')
    if locale:
        if locale == '__user__':
            locale = order.locale

    invoice = Invoice(
        order=order,
        event=order.event,
        date=date.today(),
        locale=locale
    )
    invoice = build_invoice(invoice)
    invoice_pdf(invoice.pk)
    return invoice


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

        for i, line in enumerate(invoice.footer_text.split('\n')[::-1]):
            canvas.drawCentredString(pagesize[0] / 2, 25 + (3.5 * i) * mm, line.strip())

        canvas.restoreState()

    def on_first_page(canvas, doc):
        canvas.setCreator('pretix.eu')
        canvas.setTitle(pgettext('invoice', 'Invoice {num}').format(num=invoice.number))

        canvas.saveState()
        canvas.setFont('OpenSans', 8)
        canvas.drawRightString(pagesize[0] - 20 * mm, 10 * mm, _("Page %d") % (doc.page,))

        for i, line in enumerate(invoice.footer_text.split('\n')[::-1]):
            canvas.drawCentredString(pagesize[0] / 2, 25 + (3.5 * i) * mm, line.strip())

        textobject = canvas.beginText(25 * mm, (297 - 15) * mm)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(pgettext('invoice', 'Invoice from').upper())
        canvas.drawText(textobject)

        p = Paragraph(invoice.invoice_from.strip().replace('\n', '<br />\n'), style=styles['Normal'])
        p.wrapOn(canvas, 70 * mm, 50 * mm)
        p_size = p.wrap(70 * mm, 50 * mm)
        p.drawOn(canvas, 25 * mm, (297 - 17) * mm - p_size[1])

        textobject = canvas.beginText(25 * mm, (297 - 50) * mm)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(pgettext('invoice', 'Invoice to').upper())
        canvas.drawText(textobject)

        p = Paragraph(invoice.invoice_to.strip().replace('\n', '<br />\n'), style=styles['Normal'])
        p.wrapOn(canvas, 85 * mm, 50 * mm)
        p_size = p.wrap(85 * mm, 50 * mm)
        p.drawOn(canvas, 25 * mm, (297 - 52) * mm - p_size[1])

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
        textobject.textLine(invoice.order.full_code)
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(_('Order date').upper())
        textobject.moveCursor(0, 5)
        textobject.setFont('OpenSans', 10)
        textobject.textLine(date_format(invoice.order.datetime, "DATE_FORMAT"))
        canvas.drawText(textobject)

        if invoice.event.settings.invoice_logo_image:
            logo_file = invoice.event.settings.get('invoice_logo_image', binary_file=True)
            canvas.drawImage(ImageReader(logo_file),
                             95 * mm, (297 - 38) * mm,
                             width=25 * mm, height=25 * mm,
                             preserveAspectRatio=True, anchor='n',
                             mask='auto')

        if invoice.event.settings.show_date_to:
            p_str = (
                str(invoice.event.name) + '\n' + _('{from_date}\nuntil {to_date}').format(
                    from_date=invoice.event.get_date_from_display(),
                    to_date=invoice.event.get_date_to_display())
            )
        else:
            p_str = (
                str(invoice.event.name) + '\n' + invoice.event.get_date_from_display()
            )

        p = Paragraph(p_str.strip().replace('\n', '<br />\n'), style=styles['Normal'])
        p.wrapOn(canvas, 65 * mm, 50 * mm)
        p_size = p.wrap(65 * mm, 50 * mm)
        p.drawOn(canvas, 125 * mm, (297 - 17) * mm - p_size[1])

        textobject = canvas.beginText(125 * mm, (297 - 15) * mm)
        textobject.setFont('OpenSansBd', 8)
        textobject.textLine(_('Event').upper())
        canvas.drawText(textobject)

        canvas.restoreState()

    doc = BaseDocTemplate(f.name, pagesize=pagesizes.A4,
                          leftMargin=25 * mm, rightMargin=20 * mm,
                          topMargin=20 * mm, bottomMargin=15 * mm)

    footer_length = 3.5 * len(invoice.footer_text.split('\n')) * mm
    frames_p1 = [
        Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - 75 * mm,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=footer_length,
              id='normal')
    ]
    frames = [
        Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=footer_length,
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

    if invoice.introductory_text:
        story.append(Paragraph(invoice.introductory_text, styles['Normal']))
        story.append(Spacer(1, 10 * mm))

    taxvalue_map = defaultdict(Decimal)
    grossvalue_map = defaultdict(Decimal)

    tstyledata = [
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, 0), 'OpenSansBd'),
        ('FONTNAME', (0, -1), (-1, -1), 'OpenSansBd'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]
    tdata = [(
        pgettext('invoice', 'Description'),
        pgettext('invoice', 'Tax rate'),
        pgettext('invoice', 'Net'),
        pgettext('invoice', 'Gross'),
    )]
    total = Decimal('0.00')
    for line in invoice.lines.all():
        tdata.append((
            Paragraph(line.description, styles['Normal']),
            localize(line.tax_rate) + " %",
            localize(line.net_value) + " " + invoice.event.currency,
            localize(line.gross_value) + " " + invoice.event.currency,
        ))
        taxvalue_map[line.tax_rate] += line.tax_value
        grossvalue_map[line.tax_rate] += line.gross_value
        total += line.gross_value

    tdata.append([pgettext('invoice', 'Invoice total'), '', '', localize(total) + " " + invoice.event.currency])
    colwidths = [a * doc.width for a in (.55, .15, .15, .15)]
    table = Table(tdata, colWidths=colwidths, repeatRows=1)
    table.setStyle(TableStyle(tstyledata))
    story.append(table)

    story.append(Spacer(1, 15 * mm))

    if invoice.payment_provider_text:
        story.append(Paragraph(invoice.payment_provider_text, styles['Normal']))

    if invoice.additional_text:
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
            localize(rate) + " %",
            localize((gross - tax)) + " " + invoice.event.currency,
            localize(gross) + " " + invoice.event.currency,
            localize(tax) + " " + invoice.event.currency,
        ))

    if len(tdata) > 2:
        colwidths = [a * doc.width for a in (.45, .10, .15, .15, .15)]
        table = Table(tdata, colWidths=colwidths, repeatRows=2)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)

    doc.build(story)
    return doc


@app.task(base=TransactionAwareTask)
def invoice_pdf_task(invoice: int):
    i = Invoice.objects.get(pk=invoice)
    with language(i.locale):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            _invoice_generate_german(i, f)
            f.seek(0)
            i.file.save('invoice.pdf', ContentFile(f.read()))
        i.save()
        return i.file.name


def invoice_qualified(order: Order):
    if order.total == Decimal('0.00'):
        return False
    return True


def invoice_pdf(*args, **kwargs):
    # We call this task asynchroneously, because otherwise we run into conditions where
    # the task worker tries to generate the PDF even before our database transaction
    # was committed and therefore fails to find the invoice object. The invoice_pdf_task
    # will prevent this kind of race condition.
    invoice_pdf_task.apply_async(args=args, kwargs=kwargs)


class DummyRollbackException(Exception):
    pass


def build_preview_invoice_pdf(event):
    locale = event.settings.invoice_language
    if not locale or locale == '__user__':
        locale = event.settings.locale

    with rolledback_transaction(), language(locale):
        order = event.orders.create(status=Order.STATUS_PENDING, datetime=now(),
                                    expires=now(), code="PREVIEW", total=119)
        invoice = Invoice(
            order=order, event=event, invoice_no="PREVIEW",
            date=date.today(), locale=locale
        )
        invoice.invoice_from = event.settings.get('invoice_address_from')

        introductory = event.settings.get('invoice_introductory_text', as_type=LazyI18nString)
        additional = event.settings.get('invoice_additional_text', as_type=LazyI18nString)
        footer = event.settings.get('invoice_footer_text', as_type=LazyI18nString)
        payment = _("A payment provider specific text might appear here.")

        invoice.introductory_text = str(introductory).replace('\n', '<br />')
        invoice.additional_text = str(additional).replace('\n', '<br />')
        invoice.footer_text = str(footer)
        invoice.payment_provider_text = str(payment).replace('\n', '<br />')
        invoice.invoice_to = _("John Doe\n214th Example Street\n012345 Somecity")
        invoice.file = None
        invoice.save()
        invoice.lines.all().delete()

        InvoiceLine.objects.create(
            invoice=invoice, description=_("Sample product A"),
            gross_value=119, tax_value=19,
            tax_rate=19
        )
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            _invoice_generate_german(invoice, f)
            f.seek(0)
            return f.read()
