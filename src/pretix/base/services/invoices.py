#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
from pretix.base.models import (
    ExchangeRate, Invoice, InvoiceAddress, InvoiceLine, Order, OrderFee,
)
from pretix.base.models.tax import EU_CURRENCIES
from pretix.base.services.tasks import TransactionAwareTask
from pretix.base.signals import invoice_line_text, periodic_task
from pretix.celery_app import app
from pretix.helpers.database import OF_SELF, rolledback_transaction
from pretix.helpers.models import modelcopy

logger = logging.getLogger(__name__)


def _location_oneliner(loc):
    return ', '.join([l.strip() for l in loc.splitlines() if l and l.strip()])


@transaction.atomic
def build_invoice(invoice: Invoice) -> Invoice:
    invoice.locale = invoice.event.settings.get('invoice_language', invoice.event.settings.locale)
    if invoice.locale == '__user__':
        invoice.locale = invoice.order.locale or invoice.event.settings.locale

    lp = invoice.order.payments.last()

    with language(invoice.locale, invoice.event.settings.region):
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

        invoice.introductory_text = str(introductory).replace('\n', '<br />')
        invoice.additional_text = str(additional).replace('\n', '<br />')
        invoice.footer_text = str(footer)
        invoice.payment_provider_text = str(payment).replace('\n', '<br />')
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
            ).prefetch_related('answers', 'answers__question').order_by('positionid', 'id')
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

            if invoice.event.settings.invoice_event_location and location and len(locations) > 1:
                desc += "<br />" + pgettext("invoice", "Event location: {location}").format(
                    location=_location_oneliner(location)
                )

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
                event_date_from=p.subevent.date_from if invoice.event.has_subevents else invoice.event.date_from,
                event_date_to=p.subevent.date_to if invoice.event.has_subevents else invoice.event.date_to,
                event_location=location if invoice.event.settings.invoice_event_location else None,
                tax_rate=p.tax_rate, tax_name=p.tax_rule.name if p.tax_rule else ''
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
            InvoiceLine.objects.create(
                position=i + offset,
                invoice=invoice,
                description=fee_title,
                gross_value=fee.value,
                event_date_from=None if invoice.event.has_subevents else invoice.event.date_from,
                event_date_to=None if invoice.event.has_subevents else invoice.event.date_to,
                event_location=(
                    None if invoice.event.has_subevents
                    else (str(invoice.event.location)
                          if invoice.event.settings.invoice_event_location and invoice.event.location
                          else None)
                ),
                tax_value=fee.tax_value,
                tax_rate=fee.tax_rate,
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
    cancellation.date = timezone.now().astimezone(invoice.event.timezone).date()
    cancellation.payment_provider_text = ''
    cancellation.payment_provider_stamp = ''
    cancellation.file = None
    cancellation.sent_to_organizer = None
    cancellation.sent_to_customer = None
    with language(invoice.locale, invoice.event.settings.region):
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
        date=timezone.now().astimezone(order.event.timezone).date(),
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
        with language(i.locale, i.event.settings.region):
            fname, ftype, fcontent = i.event.invoice_renderer.generate(i)
            i.file.save(fname, ContentFile(fcontent), save=False)
            i.save(update_fields=['file'])
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

    with rolledback_transaction(), language(locale, event.settings.region):
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
                        tax_rate=tax.rate
                    )
        else:
            for i in range(5):
                InvoiceLine.objects.create(
                    invoice=invoice, description=_("Sample product A"),
                    gross_value=100, tax_value=0, tax_rate=0
                )

        return event.invoice_renderer.generate(invoice)


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
                            email=i.event.settings.invoice_email_organizer,
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
                        )
                    i.sent_to_organizer = True
                else:
                    i.sent_to_organizer = False
                i.save(update_fields=['sent_to_organizer'])
