import random
import string
from datetime import date
from decimal import Decimal

from django.db import DatabaseError, models
from django.db.models import Max


def invoice_filename(instance, filename: str) -> str:
    secret = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
    return 'invoices/{org}/{ev}/{ev}-{no}-{code}-{secret}.pdf'.format(
        org=instance.event.organizer.slug, ev=instance.event.slug,
        no=instance.invoice_no, code=instance.order.code,
        secret=secret
    )


class Invoice(models.Model):
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
            raise ValueError('Any invoice needs to be connected to an order')
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
        return '%s-%05d' % (self.event.slug.upper(), self.invoice_no)

    class Meta:
        unique_together = ('event', 'invoice_no')


class InvoiceLine(models.Model):
    invoice = models.ForeignKey('Invoice', related_name='lines')
    description = models.TextField()
    gross_value = models.DecimalField(max_digits=10, decimal_places=2)
    tax_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))
