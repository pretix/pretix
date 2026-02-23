#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import inspect
import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, transaction
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
from pretix.base.invoicing.transmission import (
    get_transmission_types, transmission_providers,
)
from pretix.base.models import (
    ExchangeRate, Invoice, InvoiceAddress, InvoiceLine, Order, OrderFee,
)
from pretix.base.models.tax import EU_CURRENCIES
from pretix.base.services.tasks import (
    TransactionAwareProfiledEventTask, TransactionAwareTask,
)
from pretix.base.signals import (
    build_invoice_data, invoice_line_text, periodic_task,
)
from pretix.celery_app import app
from pretix.helpers.database import OF_SELF, rolledback_transaction
from pretix.helpers.models import modelcopy

logger = logging.getLogger(__name__)


def _location_oneliner(loc):
    return ', '.join([l.strip() for l in loc.splitlines() if l and l.strip()])


@transaction.atomic
def build_invoice(invoice: Invoice) -> Invoice:
    invoice.locale = invoice.event.settings.get('invoice_language', invoice.event.settings.locale)
    invoice.transmission_status = Invoice.TRANSMISSION_STATUS_PENDING
    if invoice.locale == '__user__':
        invoice.locale = invoice.order.locale or invoice.event.settings.locale

    lp = invoice.order.payments.last()

    min_period_start = None
    max_period_end = None
    now_dt = now()

    with (language(invoice.locale, invoice.event.settings.region)):
        invoice.invoice_from = invoice.event.settings.get('invoice_address_from')
        invoice.invoice_from_name = invoice.event.settings.get('invoice_address_from_name')
        invoice.invoice_from_zipcode = invoice.event.settings.get('invoice_address_from_zipcode')
        invoice.invoice_from_city = invoice.event.settings.get('invoice_address_from_city')
        invoice.invoice_from_state = invoice.event.settings.get('invoice_address_from_state')
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
            payment_stamp = lp.payment_provider.render_invoice_stamp(invoice.order, lp)
        else:
            payment = ""
            payment_stamp = None
        if invoice.event.settings.invoice_include_expire_date and invoice.order.status == Order.STATUS_PENDING:
            if payment:
                payment += "<br /><br />"
            payment += pgettext("invoice", "Please complete your payment before {expire_date}.").format(
                expire_date=date_format(invoice.order.expires, "SHORT_DATE_FORMAT")
            )

        invoice.introductory_text = str(introductory).replace('\n', '<br />').replace('\r', '')
        invoice.additional_text = str(additional).replace('\n', '<br />').replace('\r', '')
        invoice.footer_text = str(footer)
        invoice.payment_provider_text = str(payment).replace('\n', '<br />').replace('\r', '')
        invoice.payment_provider_stamp = str(payment_stamp) if payment_stamp else None

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
            invoice.invoice_to_is_business = ia.is_business
            invoice.invoice_to_name = ia.name
            invoice.invoice_to_street = ia.street
            invoice.invoice_to_zipcode = ia.zipcode
            invoice.invoice_to_city = ia.city
            invoice.invoice_to_country = ia.country
            invoice.invoice_to_state = ia.state
            invoice.invoice_to_beneficiary = ia.beneficiary
            invoice.invoice_to_transmission_info = ia.transmission_info or {}
            invoice.transmission_type = ia.transmission_type

            if ia.vat_id:
                invoice.invoice_to += "\n" + pgettext("invoice", "VAT-ID: %s") % ia.vat_id
                invoice.invoice_to_vat_id = ia.vat_id

            if invoice.event.settings.invoice_eu_currencies == 'True':
                cc = str(ia.country)
                if cc in EU_CURRENCIES and EU_CURRENCIES[cc] != invoice.event.currency:
                    invoice.foreign_currency_display = EU_CURRENCIES[cc]

                    if settings.FETCH_ECB_RATES:
                        rate = ExchangeRate.objects.filter(
                            source='eu:ecb:eurofxref-daily',
                            source_currency=invoice.event.currency,
                            other_currency=invoice.foreign_currency_display,
                            source_date__gt=now().date() - timedelta(days=7)
                        ).first()
                        if rate:
                            invoice.foreign_currency_rate = rate.rate.quantize(Decimal('0.0001'), ROUND_HALF_UP)
                            invoice.foreign_currency_rate_date = rate.source_date
                            invoice.foreign_currency_source = 'eu:ecb:eurofxref-daily'
                        else:
                            rate_eur_to_event = ExchangeRate.objects.filter(
                                source='eu:ecb:eurofxref-daily',
                                source_currency='EUR',
                                other_currency=invoice.event.currency,
                                source_date__gt=now().date() - timedelta(days=7)
                            ).first()
                            rate_eur_to_wanted = ExchangeRate.objects.filter(
                                source='eu:ecb:eurofxref-daily',
                                source_currency='EUR',
                                other_currency=invoice.foreign_currency_display,
                                source_date__gt=now().date() - timedelta(days=7)
                            ).first()
                            if rate_eur_to_wanted and rate_eur_to_event:
                                invoice.foreign_currency_rate = (
                                    rate_eur_to_wanted.rate / rate_eur_to_event.rate
                                ).quantize(Decimal('0.0001'), ROUND_HALF_UP)
                                invoice.foreign_currency_rate_date = min(rate_eur_to_wanted.source_date, rate_eur_to_event.source_date)
                                invoice.foreign_currency_source = 'eu:ecb:eurofxref-daily'
            elif invoice.event.settings.invoice_eu_currencies == 'CZK' and invoice.event.currency != 'CZK':
                invoice.foreign_currency_display = 'CZK'
                if settings.FETCH_ECB_RATES:
                    rate = ExchangeRate.objects.filter(
                        source='cz:cnb:rate-fixing-daily',
                        source_currency=invoice.event.currency,
                        other_currency=invoice.foreign_currency_display,
                        source_date__gt=now().date() - timedelta(days=7)
                    ).first()
                    if rate:
                        invoice.foreign_currency_rate = rate.rate.quantize(Decimal('0.0001'), ROUND_HALF_UP)
                        invoice.foreign_currency_rate_date = rate.source_date
                        invoice.foreign_currency_source = 'cz:cnb:rate-fixing-daily'

        except InvoiceAddress.DoesNotExist:
            ia = None
            invoice.invoice_to = ""

        invoice.file = None
        invoice.save()
        invoice.lines.all().delete()

        positions = list(
            invoice.order.positions.select_related('addon_to', 'item', 'tax_rule', 'subevent', 'variation').annotate(
                addon_c=Count('addons')
            ).prefetch_related(
                'answers', 'answers__options', 'answers__question', 'granted_memberships',
            ).order_by('positionid', 'id')
        )

        reverse_charge = False

        positions.sort(key=lambda p: p.sort_key)
        fees = list(invoice.order.fees.all())

        locations = {
            str((p.subevent or invoice.event).location) if (p.subevent or invoice.event).location else None
            for p in positions
        }
        if fees and invoice.event.has_subevents:
            locations.add(None)

        tax_texts = []

        if invoice.event.settings.invoice_event_location and len(locations) == 1 and list(locations)[0] is not None:
            tax_texts.append(pgettext("invoice", "Event location: {location}").format(
                location=_location_oneliner(str(list(locations)[0]))
            ))

        for i, p in enumerate(positions):
            if not invoice.event.settings.invoice_include_free and p.price == Decimal('0.00') and not p.addon_c:
                continue

            location = str((p.subevent or invoice.event).location) if (p.subevent or invoice.event).location else None

            desc = str(p.item.name)
            if p.variation:
                desc += " - " + str(p.variation.value)
            if p.addon_to_id:
                desc = "  + " + desc
            if invoice.event.settings.invoice_attendee_name and p.attendee_name:
                desc += "<br />" + pgettext("invoice", "Attendee: {name}").format(
                    name=p.attendee_name
                )

            for recv, resp in invoice_line_text.send(sender=invoice.event, position=p):
                if resp:
                    desc += "<br/>" + resp

            answers_qs = p.answers.filter(
                question__print_on_invoice=True
            ).select_related(
                'question'
            ).order_by(
                'question__position',
                'question__id'
            )
            for answ in answers_qs:
                desc += "<br />{}{} {}".format(
                    answ.question.question,
                    "" if str(answ.question.question).endswith("?") else ":",
                    answ.to_string_i18n()
                )

            if invoice.event.has_subevents:
                desc += "<br />" + pgettext("subevent", "Date: {}").format(p.subevent)

            if invoice.event.settings.invoice_event_location and location and len(locations) > 1:
                desc += "<br />" + pgettext("invoice", "Event location: {location}").format(
                    location=_location_oneliner(location)
                )

            period_start, period_end = _service_period_for_position(invoice, p, now_dt)
            min_period_start = min(min_period_start or period_start, period_start)
            max_period_end = min(max_period_end or period_end, period_end)

            InvoiceLine.objects.create(
                position=i,
                invoice=invoice,
                description=desc,
                gross_value=p.price,
                tax_value=p.tax_value,
                subevent=p.subevent,
                item=p.item,
                variation=p.variation,
                attendee_name=p.attendee_name if invoice.event.settings.invoice_attendee_name else None,
                period_start=period_start,
                period_end=period_end,
                event_location=location if invoice.event.settings.invoice_event_location else None,
                tax_rate=p.tax_rate,
                tax_code=p.tax_code,
                tax_name=p.tax_rule.name if p.tax_rule else ''
            )

            if p.tax_rule and p.tax_rule.is_reverse_charge(ia) and p.price and not p.tax_value:
                reverse_charge = True

            if p.tax_rule:
                tax_text = p.tax_rule.invoice_text(ia)
                if tax_text and tax_text not in tax_texts:
                    tax_texts.append(tax_text)

        offset = len(positions)
        for i, fee in enumerate(fees):
            if fee.fee_type == OrderFee.FEE_TYPE_OTHER and fee.description:
                fee_title = fee.description
            else:
                fee_title = _(fee.get_fee_type_display())
                if fee.description:
                    fee_title += " - " + fee.description

            if min_period_start and max_period_end:
                # Consider fees to have the same service period as the products sold
                period_start = min_period_start
                period_end = max_period_end
            else:
                # Usually can only happen if everything except a cancellation fee is removed
                if invoice.event.settings.invoice_period in ("auto", "auto_no_event", "event_date") and not invoice.event.has_subevents:
                    # Non-series event, let's be backwards-compatible and tag everything with the event period
                    period_start = invoice.event.date_from
                    period_end = invoice.event.date_to
                else:
                    # We could try to work from the canceled positions, but it doesn't really make sense. A cancellation
                    # fee is not "delivered" at the event date, it is rather effective right now.
                    period_start = period_end = now()

            InvoiceLine.objects.create(
                position=i + offset,
                invoice=invoice,
                description=fee_title,
                gross_value=fee.value,
                period_start=period_start,
                period_end=period_end,
                event_location=(
                    None if invoice.event.has_subevents
                    else (str(invoice.event.location)
                          if invoice.event.settings.invoice_event_location and invoice.event.location
                          else None)
                ),
                tax_value=fee.tax_value,
                tax_rate=fee.tax_rate,
                tax_code=fee.tax_code,
                tax_name=fee.tax_rule.name if fee.tax_rule else '',
                fee_type=fee.fee_type,
                fee_internal_type=fee.internal_type or None,
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

        build_invoice_data.send(sender=invoice.event, invoice=invoice)
        return invoice


def build_cancellation(invoice: Invoice):
    invoice.lines.all().delete()

    for line in invoice.refers.lines.all():
        line.pk = None
        line.invoice = invoice
        line.gross_value *= -1
        line.tax_value *= -1
        line.save()

    build_invoice_data.send(sender=invoice.event, invoice=invoice)
    return invoice


def _service_period_for_position(invoice, position, invoice_dt):
    if invoice.event.settings.invoice_period in ("auto", "auto_no_event"):
        if position.valid_from and position.valid_until:
            period_start = position.valid_from
            period_end = position.valid_until
        elif position.valid_from:
            period_start = position.valid_from
            period_end = position.valid_from  # weird, but we have nothing else to base this on
        elif position.valid_until:
            period_start = min(invoice.order.datetime, position.valid_until)
            period_end = position.valid_until
        elif memberships := list(position.granted_memberships.all()):
            period_start = min(m.date_start for m in memberships)
            period_end = max(m.date_end for m in memberships)
        elif invoice.event.has_subevents:
            if position.subevent:
                period_start = position.subevent.date_from
                period_end = position.subevent.date_to
            else:
                # Currently impossible case, but might not be in the future and never makes
                # sense to use the event date here
                period_start = invoice_dt
                period_end = invoice_dt
        elif invoice.event.settings.invoice_period == "auto_no_event":
            period_start = invoice_dt
            period_end = invoice_dt
        else:
            period_start = invoice.event.date_from
            period_end = invoice.event.date_to
    elif invoice.event.settings.invoice_period == "order_date":
        period_start = invoice.order.datetime
        period_end = invoice.order.datetime
    elif invoice.event.settings.invoice_period == "event_date":
        if position.subevent:
            period_start = position.subevent.date_from
            period_end = position.subevent.date_to
        else:
            period_start = invoice.event.date_from
            period_end = invoice.event.date_to
    elif invoice.event.settings.invoice_period == "invoice_date":
        period_start = period_end = invoice_dt
    else:
        raise ValueError(f"Invalid invoice period setting '{invoice.event.settings.invoice_period}'")

    if not period_end:
        period_end = period_start
    return period_start, period_end


def generate_cancellation(invoice: Invoice, trigger_pdf=True):
    if invoice.canceled:
        raise ValueError("Invoice should not be canceled twice.")
    cancellation = modelcopy(invoice)
    cancellation.pk = None
    cancellation.invoice_no = None
    cancellation.prefix = None
    cancellation.refers = invoice
    cancellation.is_cancellation = True
    cancellation.date = timezone.now().astimezone(invoice.event.timezone).date()
    cancellation.payment_provider_text = ''
    cancellation.payment_provider_stamp = ''
    cancellation.file = None
    cancellation.sent_to_organizer = None
    cancellation.transmission_provider = None
    cancellation.transmission_status = Invoice.TRANSMISSION_STATUS_PENDING
    cancellation.transmission_date = None
    with language(invoice.locale, invoice.event.settings.region):
        cancellation.invoice_from = invoice.event.settings.get('invoice_address_from')
        cancellation.invoice_from_name = invoice.event.settings.get('invoice_address_from_name')
        cancellation.invoice_from_zipcode = invoice.event.settings.get('invoice_address_from_zipcode')
        cancellation.invoice_from_city = invoice.event.settings.get('invoice_address_from_city')
        cancellation.invoice_from_state = invoice.event.settings.get('invoice_address_from_state')
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
        date=timezone.now().astimezone(order.event.timezone).date(),
    )
    invoice = build_invoice(invoice)
    if trigger_pdf:
        invoice_pdf(invoice.pk)

    if order.status == Order.STATUS_CANCELED:
        generate_cancellation(invoice, trigger_pdf)

    if order.invoice_dirty:
        order.invoice_dirty = False
        order.save(update_fields=['invoice_dirty'])

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
        with language(i.locale, i.event.settings.region):
            fname, ftype, fcontent = i.event.invoice_renderer.generate(i)
            i.file.save(fname, ContentFile(fcontent), save=False)
            i.save(update_fields=['file'])
            return i.file.name


def invoice_qualified(order: Order):
    if order.total == Decimal('0.00'):
        return False
    if order.require_approval:
        return False
    if order.sales_channel.identifier not in order.event.settings.invoice_generate_sales_channels:
        return False
    if order.status in (Order.STATUS_CANCELED, Order.STATUS_EXPIRED):
        return False
    if order.event.settings.invoice_generate_only_business:
        try:
            ia = order.invoice_address
            return ia.is_business
        except InvoiceAddress.DoesNotExist:
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

    if event.settings.invoice_period in ("auto", "auto_no_event", "event_date"):
        period_start = event.date_from
        period_end = event.date_to or event.date_from
    else:
        period_start = period_end = timezone.now()

    with rolledback_transaction(), language(locale, event.settings.region):
        order = event.orders.create(
            status=Order.STATUS_PENDING, datetime=timezone.now(),
            expires=timezone.now(), code="PREVIEW", total=100 * event.tax_rules.count(),
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        invoice = Invoice(
            order=order, event=event, invoice_no="PREVIEW",
            date=timezone.now().date(), locale=locale, organizer=event.organizer
        )
        invoice.invoice_from = event.settings.get('invoice_address_from')
        invoice.invoice_from_name = invoice.event.settings.get('invoice_address_from_name')
        invoice.invoice_from_zipcode = invoice.event.settings.get('invoice_address_from_zipcode')
        invoice.invoice_from_city = invoice.event.settings.get('invoice_address_from_city')
        invoice.invoice_from_state = invoice.event.settings.get('invoice_address_from_state')
        invoice.invoice_from_country = invoice.event.settings.get('invoice_address_from_country')
        invoice.invoice_from_tax_id = invoice.event.settings.get('invoice_address_from_tax_id')
        invoice.invoice_from_vat_id = invoice.event.settings.get('invoice_address_from_vat_id')

        introductory = event.settings.get('invoice_introductory_text', as_type=LazyI18nString)
        additional = event.settings.get('invoice_additional_text', as_type=LazyI18nString)
        footer = event.settings.get('invoice_footer_text', as_type=LazyI18nString)
        payment = _("A payment provider specific text might appear here.")

        invoice.introductory_text = str(introductory).replace('\n', '<br />').replace('\r', '')
        invoice.additional_text = str(additional).replace('\n', '<br />').replace('\r', '')
        invoice.footer_text = str(footer)
        invoice.payment_provider_text = str(payment).replace('\n', '<br />').replace('\r', '')
        invoice.payment_provider_stamp = _('paid')
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
                for j in range(5):
                    tax = tr.tax(Decimal('100.00'), base_price_is='gross')
                    InvoiceLine.objects.create(
                        invoice=invoice, description=_("Sample product {}").format(i + 1),
                        gross_value=tax.gross, tax_value=tax.tax,
                        tax_rate=tax.rate, tax_name=tax.name, tax_code=tax.code,
                        period_start=period_start,
                        period_end=period_end,
                        event_location=event.settings.invoice_event_location,
                    )
        else:
            for i in range(5):
                InvoiceLine.objects.create(
                    invoice=invoice, description=_("Sample product A"),
                    gross_value=100, tax_value=0, tax_rate=0, tax_code=None,
                    period_start=period_start,
                    period_end=period_end,
                    event_location=event.settings.invoice_event_location,
                )

        return event.invoice_renderer.generate(invoice)


def order_invoice_transmission_separately(order):
    try:
        info = order.invoice_address.transmission_info or {}
        return (
            order.invoice_address.transmission_type != "email" or
            (
                info.get("transmission_email_address") and
                order.email != info["transmission_email_address"]
            )
        )
    except InvoiceAddress.DoesNotExist:
        return False


def invoice_transmission_separately(invoice):
    if not invoice:
        return False
    try:
        info = invoice.invoice_to_transmission_info or {}
        return (
            invoice.transmission_type != "email" or
            (
                info.get("transmission_email_address") and
                invoice.order.email != info["transmission_email_address"]
            )
        )
    except InvoiceAddress.DoesNotExist:
        return False


@receiver(signal=periodic_task)
@scopes_disabled()
def send_invoices_to_organizer(sender, **kwargs):
    from pretix.base.services.mail import mail

    batch_size = 50
    # this adds some rate limiting on the number of invoices to send at the same time. If there's more, the next
    # cronjob will handle them
    max_number_of_batches = 10

    for i in range(max_number_of_batches):
        with transaction.atomic():
            qs = Invoice.objects.filter(
                sent_to_organizer__isnull=True
            ).prefetch_related('event', 'order').select_for_update(of=OF_SELF, skip_locked=connection.features.has_select_for_update_skip_locked)
            for i in qs[:batch_size]:
                if i.event.settings.invoice_email_organizer:
                    with language(i.event.settings.locale):
                        mail(
                            email=[e.strip() for e in i.event.settings.invoice_email_organizer.split(",")],
                            subject=_('New invoice: {number}').format(number=i.number),
                            template=LazyI18nString.from_gettext(_(
                                'Hello,\n\n'
                                'a new invoice for order {order} at {event} has been created, see attached.\n\n'
                                'We are sending this email because you configured us to do so in your event settings.'
                            )),
                            context={
                                'event': str(i.event),
                                'order': str(i.order),
                            },
                            locale=i.event.settings.locale,
                            event=i.event,
                            invoices=[i],
                            auto_email=True,
                            plain_text_only=True,
                        )
                    i.sent_to_organizer = True
                else:
                    i.sent_to_organizer = False
                i.save(update_fields=['sent_to_organizer'])


@receiver(signal=periodic_task)
@scopes_disabled()
def retry_stuck_invoices(sender, **kwargs):
    with transaction.atomic():
        qs = Invoice.objects.filter(
            transmission_status=Invoice.TRANSMISSION_STATUS_INFLIGHT,
            transmission_date__lte=now() - timedelta(hours=48),
        ).select_for_update(
            of=OF_SELF, skip_locked=connection.features.has_select_for_update_skip_locked
        )
        batch_size = 5000
        for invoice in qs[:batch_size]:
            invoice.transmission_status = Invoice.TRANSMISSION_STATUS_PENDING
            invoice.transmission_date = now()
            invoice.save(update_fields=["transmission_status", "transmission_date"])
            transmit_invoice.apply_async(args=(invoice.event_id, invoice.pk, True))


@receiver(signal=periodic_task)
@scopes_disabled()
def send_pending_invoices(sender, **kwargs):
    with transaction.atomic():
        # Transmit all invoices that have not been transmitted by another process if the provider enforces
        # transmission
        types = [
            tt.identifier for tt in get_transmission_types()
            if tt.enforce_transmission
        ]
        qs = Invoice.objects.filter(
            transmission_type__in=types,
            transmission_status=Invoice.TRANSMISSION_STATUS_PENDING,
            created__lte=now() - timedelta(minutes=15),
        ).select_for_update(
            of=OF_SELF, skip_locked=connection.features.has_select_for_update_skip_locked
        )
        batch_size = 5000
        for invoice in qs[:batch_size]:
            transmit_invoice.apply_async(args=(invoice.event_id, invoice.pk, False))


@app.task(base=TransactionAwareProfiledEventTask)
def transmit_invoice(sender, invoice_id, allow_retransmission=True, **kwargs):
    with transaction.atomic(durable='tests.testdummy' not in settings.INSTALLED_APPS):
        # We need durable=True for transactional correctness, but can't have it during tests
        invoice = Invoice.objects.select_for_update(of=OF_SELF).get(pk=invoice_id)

        if invoice.transmission_status == Invoice.TRANSMISSION_STATUS_INFLIGHT:
            logger.info(f"Did not transmit invoice {invoice.pk} due to being in inflight state.")
            return

        if invoice.transmission_status != Invoice.TRANSMISSION_STATUS_PENDING and not allow_retransmission:
            logger.info(f"Did not transmit invoice {invoice.pk} due to status being {invoice.transmission_status}.")
            return

        invoice.transmission_status = Invoice.TRANSMISSION_STATUS_INFLIGHT
        invoice.transmission_date = now()
        invoice.save(update_fields=["transmission_status", "transmission_date"])

    providers = sorted([
        provider
        for provider, __ in transmission_providers.filter(type=invoice.transmission_type, active_in=sender)
    ], key=lambda p: (-p.priority, p.identifier))

    provider = None
    for p in providers:
        if p.is_available(sender, invoice.invoice_to_country, invoice.invoice_to_is_business):
            provider = p
            break

    if not provider:
        invoice.set_transmission_failed(provider=None, data={"reason": "no_provider"})
        return

    if invoice.order.testmode and not provider.testmode_supported:
        invoice.transmission_status = Invoice.TRANSMISSION_STATUS_TESTMODE_IGNORED
        invoice.transmission_date = now()
        invoice.save(update_fields=["transmission_status", "transmission_date"])
        invoice.order.log_action(
            "pretix.event.order.invoice.testmode_ignored",
            data={
                "full_invoice_no": invoice.full_invoice_no,
                "transmission_provider": None,
                "transmission_type": invoice.transmission_type,
            }
        )
        return

    try:
        provider.transmit(invoice)
    except Exception as e:
        logger.exception(f"Transmission of invoice {invoice.pk} failed with exception.")
        invoice.set_transmission_failed(provider=provider.identifier, data={
            "reason": "exception",
            "exception": str(e),
        })
