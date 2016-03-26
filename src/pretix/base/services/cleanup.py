from datetime import timedelta

from django.dispatch import receiver
from django.utils.timezone import now

from ..models import CachedFile, CartPosition, InvoiceAddress
from ..signals import periodic_task


@receiver(signal=periodic_task)
def clean_cart_positions(sender, **kwargs):
    for cp in CartPosition.objects.filter(expires__lt=now() - timedelta(days=14)):
        cp.delete()
    for ia in InvoiceAddress.objects.filter(order__isnull=True, last_modified__lt=now() - timedelta(days=14)):
        ia.delete()


@receiver(signal=periodic_task)
def clean_cached_files(sender, **kwargs):
    for cf in CachedFile.objects.filter(expires__isnull=False, expires__lt=now()):
        cf.delete()
