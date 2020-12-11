import inspect
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
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import gettext as _, pgettext
from django_countries.fields import Country
from django_scopes import scope, scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.i18n import language
from pretix.base.models import (
    Invoice, InvoiceAddress, InvoiceLine, Order, OrderFee,
)
from pretix.base.models.tax import EU_CURRENCIES
from pretix.base.services.tasks import TransactionAwareTask
from pretix.base.settings import GlobalSettingsObject
from pretix.base.signals import invoice_line_text, periodic_task
from pretix.celery_app import app
from pretix.helpers.database import rolledback_transaction
from pretix.helpers.models import modelcopy

logger = logging.getLogger(__name__)


@transaction.atomic
def build_invoice(invoice: Invoice) -> Invoice:
    invoice.locale = invoice.event.settings.get('invoice_language', invoice.event.settings.locale)
    if invoice.locale == '__user__':
        invoice.locale = invoice.order.locale or invoice.event.settings.locale

    lp = invoice.order.payments.last()

    with language(invoice.locale):
        invoice.invoice_from = invoice.event.settings.get('invoice_address_from')
        invoice.invoice_from_name = invoice.event.settings.get('invoice_address_from_name')
        invoice.invoice_from_zipcode = invoice.event.settings.get('invoice_address_from_zipcode')
        invoice.invoice_from_city = invoice.event.settings.get('invoice_address_from_city')
        invoice.invoice_from_country = invoice.event.settings.get('invoice_address_from_country')
        invoice.invoice_from_tax_id = invoice.event.settings.get('invoice_address_from_tax_id')
        invoice.invoice_from_vat_id = invoice.event.settings.get('invoice_address_from_vat_id')

        introductory = invoice.event.settings.get('invoice_introductory_text', as_type=LazyI18nString)
        additional = invoice.event.settings.get('invoice_additional_text', as_type=LazyI18nString)
        footer = invoice.event.settings.get('invoice_footer_text', as_type=LazyI18nString)
        if lp and lp.payment_provider:
            if 'payment' in inspect.signature(lp.payment_provider.render_invoice_text).parameters:
                payment = str(lp.payment_provider.render_invoice_text(invoice.order, lp))
            else:
                payment = str(lp.payment_provider.render_invoice_text(invoice.order))
        else:
            payment = ""
        if invoice.event.settings.invoice_include_expire_date and invoice.order.status == Order.STATUS_PENDING:
            if payment:
                payment += "<br />"
            payment += pgettext("invoice", "Please complete your payment before {expire_date}.").format(
                expire_date=date_format(invoice.order.expires, "SHORT_DATE_FORMAT")
            )

        invoice.introductory_text = str(introductory).replace('\n', '<br />')
        invoice.additional_text = str(additional).replace('\n', '<br />')
        invoice.footer_text = str(footer)
        invoice.payment_provider_text = str(payment).replace('\n', '<br />')

        try:
            ia = invoice.order.invoice_address
            addr_template = pgettext("invoice", """{i.company}
{i.name}
{i.street}
{i.zipcode} {i.city} {state}
{country}""")
            invoice.invoice_to = "\n".join(
                a.strip() for a in addr_template.format(
                    i=ia,
                    country=ia.country.name if ia.country else ia.country_old,
                    state=ia.state_for_address
                ).split("\n") if a.strip()
            )
            invoice.internal_reference = ia.internal_reference
            invoice.custom_field = ia.custom_field
            invoice.invoice_to_company = ia.company
            invoice.invoice_to_name = ia.name
            invoice.invoice_to_street = ia.street
            invoice.invoice_to_zipcode = ia.zipcode
            invoice.invoice_to_city = ia.city
            invoice.invoice_to_country = ia.country
            invoice.invoice_to_state = ia.state
            invoice.invoice_to_beneficiary = ia.beneficiary

            if ia.vat_id:
                invoice.invoice_to += "\n" + pgettext("invoice", "VAT-ID: %s") % ia.vat_id
                invoice.invoice_to_vat_id = ia.vat_id

            cc = str(ia.country)

            if cc in EU_CURRENCIES and EU_CURRENCIES[cc] != invoice.event.currency and invoice.event.settings.invoice_eu_currencies:
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
            invoice.order.positions.select_related('addon_to', 'item', 'tax_rule', 'subevent', 'variation').annotate(
                addon_c=Count('addons')
            ).prefetch_related('answers', 'answers__question').order_by('positionid', 'id')
        )

        reverse_charge = False

        positions.sort(key=lambda p: p.sort_key)

        tax_texts = []
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
            for recv, resp in invoice_line_text.send(sender=invoice.event, position=p):
                if resp:
                    desc += "<br/>" + resp

            for answ in p.answers.all():
                if not answ.question.print_on_invoice:
                    continue
                desc += "<br />{}{} {}".format(
                    answ.question.question,
                    "" if str(answ.question.question).endswith("?") else ":",
                    str(answ)
                )

            if invoice.event.has_subevents:
                desc += "<br />" + pgettext("subevent", "Date: {}").format(p.subevent)
            InvoiceLine.objects.create(
                position=i, invoice=invoice, description=desc,
                gross_value=p.price, tax_value=p.tax_value,
                subevent=p.subevent, event_date_from=(p.subevent.date_from if p.subevent else invoice.event.date_from),
                tax_rate=p.tax_rate, tax_name=p.tax_rule.name if p.tax_rule else ''
            )

            if p.tax_rule and p.tax_rule.is_reverse_charge(ia) and p.price and not p.tax_value:
                reverse_charge = True

            if p.tax_rule:
                tax_text = p.tax_rule.invoice_text(ia)
                if tax_text and tax_text not in tax_texts:
                    tax_texts.append(tax_text)

        offset = len(positions)
        for i, fee in enumerate(invoice.order.fees.all()):
            if fee.fee_type == OrderFee.FEE_TYPE_OTHER and fee.description:
                fee_title = fee.description
            else:
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

            if fee.tax_rule and fee.tax_rule.is_reverse_charge(ia) and fee.value and not fee.tax_value:
                reverse_charge = True

            if fee.tax_rule:
                tax_text = fee.tax_rule.invoice_text(ia)
                if tax_text and tax_text not in tax_texts:
                    tax_texts.append(tax_text)

        if tax_texts:
            invoice.additional_text += "<br /><br />"
            invoice.additional_text += "<br />".join(tax_texts)
        invoice.reverse_charge = reverse_charge
        invoice.save()

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
    if invoice.canceled:
        raise ValueError("Invoice should not be canceled twice.")
    cancellation = modelcopy(invoice)
    cancellation.pk = None
    cancellation.invoice_no = None
    cancellation.prefix = None
    cancellation.refers = invoice
    cancellation.is_cancellation = True
    cancellation.date = timezone.now().date()
    cancellation.payment_provider_text = ''
    cancellation.file = None
    with language(invoice.locale):
        cancellation.invoice_from = invoice.event.settings.get('invoice_address_from')
        cancellation.invoice_from_name = invoice.event.settings.get('invoice_address_from_name')
        cancellation.invoice_from_zipcode = invoice.event.settings.get('invoice_address_from_zipcode')
        cancellation.invoice_from_city = invoice.event.settings.get('invoice_address_from_city')
        cancellation.invoice_from_country = invoice.event.settings.get('invoice_address_from_country')
        cancellation.invoice_from_tax_id = invoice.event.settings.get('invoice_address_from_tax_id')
        cancellation.invoice_from_vat_id = invoice.event.settings.get('invoice_address_from_vat_id')
    cancellation.save()

    cancellation = build_cancellation(cancellation)
    if trigger_pdf:
        invoice_pdf(cancellation.pk)
    return cancellation


def regenerate_invoice(invoice: Invoice):
    if invoice.shredded:
        return invoice
    if invoice.is_cancellation:
        invoice = build_cancellation(invoice)
    else:
        invoice = build_invoice(invoice)
    invoice_pdf(invoice.pk)
    return invoice


def generate_invoice(order: Order, trigger_pdf=True):
    invoice = Invoice(
        order=order,
        event=order.event,
        organizer=order.event.organizer,
        date=timezone.now().date(),
    )
    invoice = build_invoice(invoice)
    if trigger_pdf:
        invoice_pdf(invoice.pk)

    if order.status == Order.STATUS_CANCELED:
        generate_cancellation(invoice, trigger_pdf)

    return invoice


@app.task(base=TransactionAwareTask)
def invoice_pdf_task(invoice: int):
    with scopes_disabled():
        i = Invoice.objects.get(pk=invoice)
    with scope(organizer=i.order.event.organizer):
        if i.shredded:
            return None
        if i.file:
            i.file.delete()
        with language(i.locale):
            fname, ftype, fcontent = i.event.invoice_renderer.generate(i)
            i.file.save(fname, ContentFile(fcontent))
            i.save()
            return i.file.name


def invoice_qualified(order: Order):
    if order.total == Decimal('0.00') or order.require_approval or \
            order.sales_channel not in order.event.settings.get('invoice_generate_sales_channels'):
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
                                    expires=timezone.now(), code="PREVIEW", total=100 * event.tax_rules.count())
        invoice = Invoice(
            order=order, event=event, invoice_no="PREVIEW",
            date=timezone.now().date(), locale=locale, organizer=event.organizer
        )
        invoice.invoice_from = event.settings.get('invoice_address_from')
        invoice.invoice_from_name = invoice.event.settings.get('invoice_address_from_name')
        invoice.invoice_from_zipcode = invoice.event.settings.get('invoice_address_from_zipcode')
        invoice.invoice_from_city = invoice.event.settings.get('invoice_address_from_city')
        invoice.invoice_from_country = invoice.event.settings.get('invoice_address_from_country')
        invoice.invoice_from_tax_id = invoice.event.settings.get('invoice_address_from_tax_id')
        invoice.invoice_from_vat_id = invoice.event.settings.get('invoice_address_from_vat_id')

        introductory = event.settings.get('invoice_introductory_text', as_type=LazyI18nString)
        additional = event.settings.get('invoice_additional_text', as_type=LazyI18nString)
        footer = event.settings.get('invoice_footer_text', as_type=LazyI18nString)
        payment = _("A payment provider specific text might appear here.")

        invoice.introductory_text = str(introductory).replace('\n', '<br />')
        invoice.additional_text = str(additional).replace('\n', '<br />')
        invoice.footer_text = str(footer)
        invoice.payment_provider_text = str(payment).replace('\n', '<br />')
        invoice.invoice_to_name = _("John Doe")
        invoice.invoice_to_street = _("214th Example Street")
        invoice.invoice_to_zipcode = _("012345")
        invoice.invoice_to_city = _('Sample city')
        invoice.invoice_to_country = Country('DE')
        invoice.invoice_to = '{}\n{}\n{} {}'.format(
            invoice.invoice_to_name, invoice.invoice_to_street,
            invoice.invoice_to_zipcode, invoice.invoice_to_city
        )
        invoice.invoice_to_beneficiary = ''
        invoice.file = None
        invoice.save()
        invoice.lines.all().delete()

        if event.tax_rules.exists():
            for i, tr in enumerate(event.tax_rules.all()):
                tax = tr.tax(Decimal('100.00'), base_price_is='gross')
                InvoiceLine.objects.create(
                    invoice=invoice, description=_("Sample product {}").format(i + 1),
                    gross_value=tax.gross, tax_value=tax.tax,
                    tax_rate=tax.rate
                )
        else:
            InvoiceLine.objects.create(
                invoice=invoice, description=_("Sample product A"),
                gross_value=100, tax_value=0, tax_rate=0
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
