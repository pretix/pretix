import copy
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import pgettext, ugettext as _
from i18nfield.strings import LazyI18nString

from pretix.base.i18n import language
from pretix.base.models import Invoice, InvoiceAddress, InvoiceLine, Order
from pretix.base.services.async import TransactionAwareTask
from pretix.celery_app import app
from pretix.helpers.database import rolledback_transaction


@transaction.atomic
def build_invoice(invoice: Invoice) -> Invoice:
    with language(invoice.locale):
        payment_provider = invoice.event.get_payment_providers().get(invoice.order.payment_provider)

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

        positions = list(
            invoice.order.positions.select_related('addon_to', 'item', 'variation').annotate(
                addon_c=Count('addons')
            )
        )
        positions.sort(key=lambda p: p.sort_key)
        for p in positions:
            if not invoice.event.settings.invoice_include_free and p.price == Decimal('0.00') and not p.addon_c:
                continue

            desc = str(p.item.name)
            if p.variation:
                desc += " - " + str(p.variation.value)
            if p.addon_to_id:
                desc = "  + " + desc
            InvoiceLine.objects.create(
                invoice=invoice, description=desc,
                gross_value=p.price, tax_value=p.tax_value,
                tax_rate=p.tax_rate
            )

        if invoice.order.payment_fee:
            InvoiceLine.objects.create(
                invoice=invoice,
                description=_('Payment via {method}').format(method=str(payment_provider.verbose_name)),
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
    cancellation.date = timezone.now().date()
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
        date=timezone.now().date(),
        locale=locale
    )
    invoice = build_invoice(invoice)
    invoice_pdf(invoice.pk)
    return invoice


@app.task(base=TransactionAwareTask)
def invoice_pdf_task(invoice: int):
    i = Invoice.objects.get(pk=invoice)
    with language(i.locale):
        fname, ftype, fcontent = i.event.invoice_renderer.generate(i)
        i.file.save(fname, ContentFile(fcontent))
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
        order = event.orders.create(status=Order.STATUS_PENDING, datetime=timezone.now(),
                                    expires=timezone.now(), code="PREVIEW", total=119)
        invoice = Invoice(
            order=order, event=event, invoice_no="PREVIEW",
            date=timezone.now().date(), locale=locale
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
        return event.invoice_renderer.generate(invoice)
