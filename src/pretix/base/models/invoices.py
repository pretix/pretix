import random
import string
from datetime import date
from decimal import Decimal

from django.db import DatabaseError, models
from django.db.models import Max


def invoice_filename(instance, filename: str) -> str:
    secret = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
    return 'invoices/{org}/{ev}/{ev}-{no:05d}-{code}-{secret}.pdf'.format(
        org=instance.event.organizer.slug, ev=instance.event.slug,
        no=instance.invoice_no, code=instance.order.code,
        secret=secret
    )


class Invoice(models.Model):
    """
    Represents an invoice that is issued because of an order. Because invoices are legally required
    not to change, this object duplicates a lot of data (e.g. the invoice address).

    :param order: The associated order
    :type order: Order
    :param event: The event this belongs to (for convenience)
    :type event: Event
    :param invoice_no: The human-readable, event-unique invoice number
    :type invoice_no: int
    :param is_cancellation: Whether or not this is a cancellation instead of an invoice
    :type is_cancellation: bool
    :param refers: A link to another invoice this invoice refers to, e.g. the cancelled invoice in a cancellation
    :type refers: Invoice
    :param invoice_from: The sender address
    :type invoice_from: str
    :param invoice_to: The receiver address
    :type invoice_to: str
    :param date: The invoice date
    :type date: date
    :param locale: The locale in which the invoice should be printed
    :type locale: str
    :param additional_text: Additional text for the invoice
    :type additional_text: str
    :param file: The filename of the rendered invoice
    :type file: File
    """
    order = models.ForeignKey('Order', related_name='invoices', db_index=True)
    event = models.ForeignKey('Event', related_name='invoices', db_index=True)
    invoice_no = models.PositiveIntegerField(db_index=True)
    is_cancellation = models.BooleanField(default=False)
    refers = models.ForeignKey('Invoice', related_name='refered', null=True, blank=True)
    invoice_from = models.TextField()
    invoice_to = models.TextField()
    date = models.DateField(default=date.today)
    locale = models.CharField(max_length=50, default='en')
    additional_text = models.TextField(blank=True)
    file = models.FileField(null=True, blank=True, upload_to=invoice_filename)

    def save(self, *args, **kwargs):
        if not self.order:
            raise ValueError('Every invoice needs to be connected to an order')
        if not self.event:
            self.event = self.order.event
        if not self.invoice_no:
            for i in range(10):
                self.invoice_no = (Invoice.objects.filter(
                    event=self.event).aggregate(m=Max('invoice_no'))['m'] or 0) + 1
                try:
                    return super().save(*args, **kwargs)
                except DatabaseError:
                    # Suppress duplicate key errors and try again
                    if i == 9:
                        raise
        return super().save(*args, **kwargs)

    @property
    def number(self):
        """
        Returns the invoice number in a human-readable string with the event slug prepended.
        """
        return '%s-%05d' % (self.event.slug.upper(), self.invoice_no)

    class Meta:
        unique_together = ('event', 'invoice_no')


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
    """
    invoice = models.ForeignKey('Invoice', related_name='lines')
    description = models.TextField()
    gross_value = models.DecimalField(max_digits=10, decimal_places=2)
    tax_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
