import string
from decimal import Decimal

from django.db import DatabaseError, models, transaction
from django.db.models import Max
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import pgettext
from django_countries.fields import CountryField


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
    :param footer_text: A footer text, displayed smaller and centered on every page
    :type footer_text: str
    :param foreign_currency_display: A different currency that taxes should also be displayed in.
    :type foreign_currency_display: str
    :param foreign_currency_rate: The rate of a foreign currency that the taxes should be displayed in.
    :type foreign_currency_rate: Decimal
    :param foreign_currency_rate_date: The date of the foreign currency exchange rates.
    :type foreign_currency_rate_date: date
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
    invoice_from_country = CountryField(null=True)
    invoice_from_tax_id = models.CharField(max_length=190, null=True)
    invoice_from_vat_id = models.CharField(max_length=190, null=True)
    invoice_to = models.TextField()
    invoice_to_company = models.TextField(null=True)
    invoice_to_name = models.TextField(null=True)
    invoice_to_street = models.TextField(null=True)
    invoice_to_zipcode = models.CharField(max_length=190, null=True)
    invoice_to_city = models.TextField(null=True)
    invoice_to_country = CountryField(null=True)
    invoice_to_vat_id = models.TextField(null=True)
    date = models.DateField(default=today)
    locale = models.CharField(max_length=50, default='en')
    introductory_text = models.TextField(blank=True)
    additional_text = models.TextField(blank=True)
    reverse_charge = models.BooleanField(default=False)
    payment_provider_text = models.TextField(blank=True)
    footer_text = models.TextField(blank=True)
    foreign_currency_display = models.CharField(max_length=50, null=True, blank=True)
    foreign_currency_rate = models.DecimalField(decimal_places=4, max_digits=10, null=True, blank=True)
    foreign_currency_rate_date = models.DateField(null=True, blank=True)
    shredded = models.BooleanField(default=False)

    file = models.FileField(null=True, blank=True, upload_to=invoice_filename, max_length=255)
    internal_reference = models.TextField(blank=True)

    @staticmethod
    def _to_numeric_invoice_number(number):
        return '{:05d}'.format(int(number))

    @property
    def full_invoice_from(self):
        parts = [
            self.invoice_from_name,
            self.invoice_from,
            (self.invoice_from_zipcode or "") + " " + (self.invoice_from_city or ""),
            str(self.invoice_from_country),
            pgettext("invoice", "VAT-ID: %s" % self.invoice_from_vat_id) if self.invoice_from_vat_id else "",
            pgettext("invoice", "Tax ID: %s" % self.invoice_from_tax_id) if self.invoice_from_tax_id else "",
        ]
        return '\n'.join([p.strip() for p in parts if p and p.strip()])

    def _get_numeric_invoice_number(self):
        numeric_invoices = Invoice.objects.filter(
            event__organizer=self.event.organizer,
            prefix=self.prefix,
        ).exclude(invoice_no__contains='-').annotate(
            numeric_number=Cast('invoice_no', models.IntegerField())
        ).aggregate(
            max=Max('numeric_number')
        )['max'] or 0
        return self._to_numeric_invoice_number(numeric_invoices + 1)

    def _get_invoice_number_from_order(self):
        return '{order}-{count}'.format(
            order=self.order.code,
            count=Invoice.objects.filter(event=self.event, order=self.order).count() + 1,
        )

    def save(self, *args, **kwargs):
        if not self.order:
            raise ValueError('Every invoice needs to be connected to an order')
        if not self.event:
            self.event = self.order.event
        if not self.organizer:
            self.organizer = self.order.event.organizer
        if not self.prefix:
            self.prefix = self.event.settings.invoice_numbers_prefix or (self.event.slug.upper() + '-')
        if not self.invoice_no:
            for i in range(10):
                if self.event.settings.get('invoice_numbers_consecutive'):
                    self.invoice_no = self._get_numeric_invoice_number()
                else:
                    self.invoice_no = self._get_invoice_number_from_order()
                try:
                    with transaction.atomic():
                        return super().save(*args, **kwargs)
                except DatabaseError:
                    # Suppress duplicate key errors and try again
                    if i == 9:
                        raise

        self.full_invoice_no = self.prefix + self.invoice_no
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
    """
    invoice = models.ForeignKey('Invoice', related_name='lines', on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)
    description = models.TextField()
    gross_value = models.DecimalField(max_digits=10, decimal_places=2)
    tax_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
    tax_name = models.CharField(max_length=190)

    @property
    def net_value(self):
        return self.gross_value - self.tax_value

    class Meta:
        ordering = ('position', 'pk')
