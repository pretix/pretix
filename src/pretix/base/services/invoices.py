import copy
import json
import logging
import urllib.error
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import vat_moss.exchange_rates
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count
from django.dispatch import receiver
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import pgettext, ugettext as _
from i18nfield.strings import LazyI18nString

from pretix.base.i18n import language
from pretix.base.models import Invoice, InvoiceAddress, InvoiceLine, Order
from pretix.base.models.tax import EU_CURRENCIES
from pretix.base.services.async import TransactionAwareTask
from pretix.base.settings import GlobalSettingsObject
from pretix.base.signals import periodic_task
from pretix.celery_app import app
from pretix.helpers.database import rolledback_transaction

logger = logging.getLogger(__name__)


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
            ia = invoice.order.invoice_address
            addr_template = pgettext("invoice", """{i.company}
{i.name}
{i.street}
{i.zipcode} {i.city}
{country}""")
            invoice.invoice_to = addr_template.format(
                i=ia,
                country=ia.country.name if ia.country else ia.country_old
            ).strip()
            invoice.internal_reference = ia.internal_reference
            if ia.vat_id:
                invoice.invoice_to += "\n" + pgettext("invoice", "VAT-ID: %s") % ia.vat_id

            cc = str(ia.country)

            if cc in EU_CURRENCIES and EU_CURRENCIES[cc] != invoice.event.currency:
                invoice.foreign_currency_display = EU_CURRENCIES[cc]

                if settings.FETCH_ECB_RATES:
                    gs = GlobalSettingsObject()
                    rates_date = gs.settings.get('ecb_rates_date', as_type=date)
                    rates_dict = gs.settings.get('ecb_rates_dict', as_type=dict)
                    convert = (
                        rates_date and rates_dict and
                        rates_date > (now() - timedelta(days=7)).date() and
                        invoice.event.currency in rates_dict and
                        invoice.foreign_currency_display in rates_dict
                    )
                    if convert:
                        invoice.foreign_currency_rate = (
                            Decimal(rates_dict[invoice.foreign_currency_display])
                            / Decimal(rates_dict[invoice.event.currency])
                        ).quantize(Decimal('0.0001'), ROUND_HALF_UP)
                        invoice.foreign_currency_rate_date = rates_date

        except InvoiceAddress.DoesNotExist:
            ia = None
            invoice.invoice_to = ""

        invoice.file = None
        invoice.save()
        invoice.lines.all().delete()

        positions = list(
            invoice.order.positions.select_related('addon_to', 'item', 'tax_rule', 'variation').annotate(
                addon_c=Count('addons')
            )
        )

        reverse_charge = False

        positions.sort(key=lambda p: p.sort_key)
        for i, p in enumerate(positions):
            if not invoice.event.settings.invoice_include_free and p.price == Decimal('0.00') and not p.addon_c:
                continue

            desc = str(p.item.name)
            if p.variation:
                desc += " - " + str(p.variation.value)
            if p.addon_to_id:
                desc = "  + " + desc
            if invoice.event.settings.invoice_attendee_name and p.attendee_name:
                desc += "<br />" + pgettext("invoice", "Attendee: {name}").format(name=p.attendee_name)
            InvoiceLine.objects.create(
                position=i, invoice=invoice, description=desc,
                gross_value=p.price, tax_value=p.tax_value,
                tax_rate=p.tax_rate, tax_name=p.tax_rule.name if p.tax_rule else ''
            )

            if p.tax_rule and p.tax_rule.is_reverse_charge(ia) and p.price and not p.tax_value:
                reverse_charge = True

        if reverse_charge:
            if invoice.additional_text:
                invoice.additional_text += "<br /><br />"
            invoice.additional_text += pgettext(
                "invoice",
                "Reverse Charge: According to Article 194, 196 of Council Directive 2006/112/EEC, VAT liability "
                "rests with the service recipient."
            )
            invoice.save()

        offset = len(positions)
        for i, fee in enumerate(invoice.order.fees.all()):
            fee_title = _(fee.get_fee_type_display())
            if fee.description:
                fee_title += " - " + fee.description
            InvoiceLine.objects.create(
                position=i + offset,
                invoice=invoice,
                description=fee_title,
                gross_value=fee.value,
                tax_value=fee.tax_value,
                tax_rate=fee.tax_rate,
                tax_name=fee.tax_rule.name if fee.tax_rule else ''
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


def generate_cancellation(invoice: Invoice, trigger_pdf=True):
    cancellation = copy.copy(invoice)
    cancellation.pk = None
    cancellation.invoice_no = None
    cancellation.prefix = None
    cancellation.refers = invoice
    cancellation.is_cancellation = True
    cancellation.date = timezone.now().date()
    cancellation.payment_provider_text = ''
    cancellation.save()

    cancellation = build_cancellation(cancellation)
    if trigger_pdf:
        invoice_pdf(cancellation.pk)
    return cancellation


def regenerate_invoice(invoice: Invoice):
    if invoice.is_cancellation:
        invoice = build_cancellation(invoice)
    else:
        invoice = build_invoice(invoice)
    invoice_pdf(invoice.pk)
    return invoice


def generate_invoice(order: Order, trigger_pdf=True):
    locale = order.event.settings.get('invoice_language')
    if locale:
        if locale == '__user__':
            locale = order.locale

    invoice = Invoice(
        order=order,
        event=order.event,
        organizer=order.event.organizer,
        date=timezone.now().date(),
        locale=locale
    )
    invoice = build_invoice(invoice)
    if trigger_pdf:
        invoice_pdf(invoice.pk)

    if order.status in (Order.STATUS_CANCELED, Order.STATUS_REFUNDED):
        generate_cancellation(invoice, trigger_pdf)

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
            date=timezone.now().date(), locale=locale, organizer=event.organizer
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


@receiver(signal=periodic_task)
def fetch_ecb_rates(sender, **kwargs):
    if not settings.FETCH_ECB_RATES:
        return

    gs = GlobalSettingsObject()
    if gs.settings.ecb_rates_date == now().strftime("%Y-%m-%d"):
        return

    try:
        date, rates = vat_moss.exchange_rates.fetch()
        gs.settings.ecb_rates_date = date
        gs.settings.ecb_rates_dict = json.dumps(rates, cls=DjangoJSONEncoder)
    except urllib.error.URLError:
        logger.exception('Could not retrieve rates from ECB')
