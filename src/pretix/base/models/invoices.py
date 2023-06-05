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
# This file contains Apache-licensed contributions copyrighted by: Flavia Bastos, Jakob Schnell, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import string
from decimal import Decimal

import pycountry
from django.db import DatabaseError, models, transaction
from django.db.models import Max
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import pgettext
from django_scopes import ScopedManager

from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS
from pretix.helpers.countries import FastCountryField


def invoice_filename(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'invoices/{org}/{ev}/{no}-{code}-{secret}.{ext}'.format(
        org=instance.event.organizer.slug, ev=instance.event.slug,
        no=instance.number, code=instance.order.code, secret=secret,
        ext=filename.split('.')[-1]
    )


def today():
    return timezone.now().date()


class Invoice(models.Model):
    """
    Represents an invoice that is issued because of an order. Because invoices are legally required
    not to change, this object duplicates a lot of data (e.g. the invoice address).

    :param order: The associated order
    :type order: Order
    :param event: The event this belongs to (for convenience)
    :type event: Event
    :param organizer: The organizer this belongs to (redundant, for enforcing uniqueness)
    :type organizer: Organizer
    :param invoice_no: The human-readable, event-unique invoice number
    :type invoice_no: int
    :param is_cancellation: Whether or not this is a cancellation instead of an invoice
    :type is_cancellation: bool
    :param refers: A link to another invoice this invoice refers to, e.g. the canceled invoice in a cancellation
    :type refers: Invoice
    :param invoice_from: The sender address
    :type invoice_from: str
    :param invoice_to: The receiver address
    :type invoice_to: str
    :param full_invoice_no: The full invoice number (for performance reasons only)
    :type full_invoice_no: str
    :param date: The invoice date
    :type date: date
    :param locale: The locale in which the invoice should be printed
    :type locale: str
    :param introductory_text: Introductory text for the invoice, e.g. for a greeting
    :type introductory_text: str
    :param additional_text: Additional text for the invoice
    :type additional_text: str
    :param payment_provider_text: A payment provider specific text
    :type payment_provider_text: str
    :param payment_provider_stamp: A payment provider specific stamp
    :type payment_provider_stamp: str
    :param footer_text: A footer text, displayed smaller and centered on every page
    :type footer_text: str
    :param foreign_currency_display: A different currency that taxes should also be displayed in.
    :type foreign_currency_display: str
    :param foreign_currency_rate: The rate of a foreign currency that the taxes should be displayed in.
    :type foreign_currency_rate: Decimal
    :param foreign_currency_rate_date: The date of the foreign currency exchange rates.
    :type foreign_currency_rate_date: date
    :param foreign_currency_rate_source: The source of the foreign currency rate.
    :type foreign_currency_rate_source: str
    :param file: The filename of the rendered invoice
    :type file: File
    """
    order = models.ForeignKey('Order', related_name='invoices', db_index=True, on_delete=models.CASCADE)
    organizer = models.ForeignKey('Organizer', related_name='invoices', db_index=True, on_delete=models.PROTECT)
    event = models.ForeignKey('Event', related_name='invoices', db_index=True, on_delete=models.CASCADE)

    prefix = models.CharField(max_length=160, db_index=True)
    invoice_no = models.CharField(max_length=19, db_index=True)
    full_invoice_no = models.CharField(max_length=190, db_index=True)

    is_cancellation = models.BooleanField(default=False)
    refers = models.ForeignKey('Invoice', related_name='refered', null=True, blank=True, on_delete=models.CASCADE)

    invoice_from = models.TextField()
    invoice_from_name = models.CharField(max_length=190, null=True)
    invoice_from_zipcode = models.CharField(max_length=190, null=True)
    invoice_from_city = models.CharField(max_length=190, null=True)
    invoice_from_country = FastCountryField(null=True)
    invoice_from_tax_id = models.CharField(max_length=190, null=True)
    invoice_from_vat_id = models.CharField(max_length=190, null=True)

    invoice_to = models.TextField()
    invoice_to_company = models.TextField(null=True)
    invoice_to_name = models.TextField(null=True)
    invoice_to_street = models.TextField(null=True)
    invoice_to_zipcode = models.CharField(max_length=190, null=True)
    invoice_to_city = models.TextField(null=True)
    invoice_to_state = models.CharField(max_length=190, null=True)
    invoice_to_country = FastCountryField(null=True)
    invoice_to_vat_id = models.TextField(null=True)
    invoice_to_beneficiary = models.TextField(null=True)
    internal_reference = models.TextField(blank=True)
    custom_field = models.CharField(max_length=255, null=True)

    date = models.DateField(default=today)
    locale = models.CharField(max_length=50, default='en')
    introductory_text = models.TextField(blank=True)
    additional_text = models.TextField(blank=True)
    reverse_charge = models.BooleanField(default=False)
    payment_provider_text = models.TextField(blank=True)
    payment_provider_stamp = models.CharField(max_length=100, null=True, blank=True)
    footer_text = models.TextField(blank=True)

    foreign_currency_display = models.CharField(max_length=50, null=True, blank=True)
    foreign_currency_rate = models.DecimalField(decimal_places=4, max_digits=13, null=True, blank=True)
    foreign_currency_rate_date = models.DateField(null=True, blank=True)
    foreign_currency_source = models.CharField(max_length=100, null=True, blank=True)

    shredded = models.BooleanField(default=False)

    # The field sent_to_organizer records whether this invocie was already sent to the organizer by a configured
    # mechanism such as email.
    # NULL: The cronjob that handles sending did not yet run.
    # True: The invoice was sent.
    # False: The invoice wasn't sent and never will, because sending was not configured at the time of the check.
    sent_to_organizer = models.BooleanField(null=True, blank=True)

    sent_to_customer = models.DateTimeField(null=True, blank=True)

    file = models.FileField(null=True, blank=True, upload_to=invoice_filename, max_length=255)

    objects = ScopedManager(organizer='event__organizer')

    @staticmethod
    def _to_numeric_invoice_number(number, places):
        return ('{:0%dd}' % places).format(int(number))

    @property
    def full_invoice_from(self):
        taxidrow = ""
        if self.invoice_from_tax_id:
            if str(self.invoice_from_country) == "AU":
                taxidrow = "ABN: %s" % self.invoice_from_tax_id
            else:
                taxidrow = pgettext("invoice", "Tax ID: %s") % self.invoice_from_tax_id
        parts = [
            self.invoice_from_name,
            self.invoice_from,
            (self.invoice_from_zipcode or "") + " " + (self.invoice_from_city or ""),
            self.invoice_from_country.name if self.invoice_from_country else "",
            pgettext("invoice", "VAT-ID: %s") % self.invoice_from_vat_id if self.invoice_from_vat_id else "",
            taxidrow,
        ]
        return '\n'.join([p.strip() for p in parts if p and p.strip()])

    @property
    def address_invoice_from(self):
        parts = [
            self.invoice_from_name,
            self.invoice_from,
            (self.invoice_from_zipcode or "") + " " + (self.invoice_from_city or ""),
            self.invoice_from_country.name if self.invoice_from_country else "",
        ]
        return '\n'.join([p.strip() for p in parts if p and p.strip()])

    @property
    def address_invoice_to(self):
        if self.invoice_to and not self.invoice_to_company and not self.invoice_to_name:
            return self.invoice_to

        state_name = ""
        if self.invoice_to_state:
            state_name = self.invoice_to_state
            if str(self.invoice_to_country) in COUNTRIES_WITH_STATE_IN_ADDRESS:
                if COUNTRIES_WITH_STATE_IN_ADDRESS[str(self.invoice_to_country)][1] == 'long':
                    try:
                        state_name = pycountry.subdivisions.get(
                            code='{}-{}'.format(self.invoice_to_country, self.invoice_to_state)
                        ).name
                    except:
                        pass

        parts = [
            self.invoice_to_company,
            self.invoice_to_name,
            self.invoice_to_street,
            ((self.invoice_to_zipcode or "") + " " + (self.invoice_to_city or "") + " " + (state_name or "")).strip(),
            self.invoice_to_country.name if self.invoice_to_country else "",
        ]
        return '\n'.join([p.strip() for p in parts if p and p.strip()])

    def _get_numeric_invoice_number(self, c_length):
        numeric_invoices = Invoice.objects.filter(
            event__organizer=self.event.organizer,
            prefix=self.prefix,
        ).exclude(invoice_no__contains='-').annotate(
            numeric_number=Cast('invoice_no', models.IntegerField())
        ).aggregate(
            max=Max('numeric_number')
        )['max'] or 0
        return self._to_numeric_invoice_number(numeric_invoices + 1, c_length)

    def _get_invoice_number_from_order(self):
        return '{order}-{count}'.format(
            order=self.order.code,
            count=Invoice.objects.filter(event=self.event, prefix=self.prefix, invoice_no__startswith=f"{self.order.code}-", order=self.order).count() + 1,
        )

    def save(self, *args, **kwargs):
        if not self.order:
            raise ValueError('Every invoice needs to be connected to an order')
        if not self.event:
            self.event = self.order.event
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'event'}.union(kwargs['update_fields'])
        if not self.organizer:
            self.organizer = self.order.event.organizer
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'organizer'}.union(kwargs['update_fields'])
        if not self.prefix:
            self.prefix = self.event.settings.invoice_numbers_prefix or (self.event.slug.upper() + '-')
            if self.is_cancellation:
                self.prefix = self.event.settings.invoice_numbers_prefix_cancellations or self.prefix
            if '%' in self.prefix:
                self.prefix = self.date.strftime(self.prefix)
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'prefix'}.union(kwargs['update_fields'])

        if not self.invoice_no:
            if self.order.testmode:
                self.prefix += 'TEST-'
            for i in range(10):
                if self.event.settings.get('invoice_numbers_consecutive'):
                    self.invoice_no = self._get_numeric_invoice_number(self.event.settings.invoice_numbers_counter_length)
                else:
                    self.invoice_no = self._get_invoice_number_from_order()
                try:
                    with transaction.atomic():
                        self.full_invoice_no = self.prefix + self.invoice_no
                        return super().save(*args, **kwargs)
                except DatabaseError:
                    # Suppress duplicate key errors and try again
                    if i == 9:
                        raise
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'invoice_no'}.union(kwargs['update_fields'])

        if self.full_invoice_no != self.prefix + self.invoice_no:
            self.full_invoice_no = self.prefix + self.invoice_no
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'full_invoice_no'}.union(kwargs['update_fields'])
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Deleting an Invoice would allow for the creation of another Invoice object
        with the same invoice_no as the deleted one. For various reasons, invoice_no
        should be reliably unique for an event.
        """
        raise Exception('Invoices cannot be deleted, to guarantee uniqueness of Invoice.invoice_no in any event.')

    @property
    def number(self):
        """
        Returns the invoice number in a human-readable string with the event slug prepended.
        """
        return '{prefix}{code}'.format(
            prefix=self.prefix,
            code=self.invoice_no
        )

    @cached_property
    def canceled(self):
        return self.refered.filter(is_cancellation=True).exists()

    class Meta:
        unique_together = ('organizer', 'prefix', 'invoice_no')
        ordering = ('date', 'invoice_no',)

    def __repr__(self):
        return '<Invoice {} / {}>'.format(self.full_invoice_no, self.pk)

    def __str__(self):
        return self.full_invoice_no


class InvoiceLine(models.Model):
    """
    One position listed on an Invoice.

    :param invoice: The invoice this belongs to
    :type invoice: Invoice
    :param description: The item description
    :type description: str
    :param gross_value: The gross value
    :type gross_value: decimal.Decimal
    :param tax_value: The included tax (as an absolute value)
    :type tax_value: decimal.Decimal
    :param tax_rate: The applied tax rate in percent
    :type tax_rate: decimal.Decimal
    :param tax_name: The name of the applied tax rate
    :type tax_name: str
    :param subevent: The subevent this line refers to
    :type subevent: SubEvent
    :param event_date_from: Event date of the (sub)event at the time the invoice was created
    :type event_date_from: datetime
    :param event_date_to: Event end date of the (sub)event at the time the invoice was created
    :type event_date_to: datetime
    :param event_location: Event location of the (sub)event at the time the invoice was created
    :type event_location: str
    :param item: The item this line refers to
    :type item: Item
    :param variation: The variation this line refers to
    :type variation: ItemVariation
    :param attendee_name: The attendee name at the time the invoice was created
    :type attendee_name: str
    """
    invoice = models.ForeignKey('Invoice', related_name='lines', on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)
    description = models.TextField()
    gross_value = models.DecimalField(max_digits=13, decimal_places=2)
    tax_value = models.DecimalField(max_digits=13, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
    tax_name = models.CharField(max_length=190)
    subevent = models.ForeignKey('SubEvent', null=True, blank=True, on_delete=models.PROTECT)
    event_date_from = models.DateTimeField(null=True)
    event_date_to = models.DateTimeField(null=True)
    event_location = models.TextField(null=True, blank=True)
    item = models.ForeignKey('Item', null=True, blank=True, on_delete=models.PROTECT)
    variation = models.ForeignKey('ItemVariation', null=True, blank=True, on_delete=models.PROTECT)
    attendee_name = models.TextField(null=True, blank=True)
    fee_type = models.CharField(max_length=190, null=True, blank=True)
    fee_internal_type = models.CharField(max_length=190, null=True, blank=True)

    @property
    def net_value(self):
        return self.gross_value - self.tax_value

    class Meta:
        ordering = ('position', 'pk')

    def __str__(self):
        return 'Line {} of invoice {}'.format(self.position, self.invoice)
