from datetime import timedelta

from django.dispatch import receiver
from django.utils.timezone import now

from pretix.base.models import CachedCombinedTicket, CachedTicket

from ..models import CachedFile, CartPosition, InvoiceAddress
from ..signals import periodic_task


@receiver(signal=periodic_task)
def clean_cart_positions(sender, **kwargs):
    for cp in CartPosition.objects.filter(expires__lt=now() - timedelta(days=14), addon_to__isnull=False):
        cp.delete()
    for cp in CartPosition.objects.filter(expires__lt=now() - timedelta(days=14), addon_to__isnull=True):
        cp.delete()
    for ia in InvoiceAddress.objects.filter(order__isnull=True, last_modified__lt=now() - timedelta(days=14)):
        ia.delete()


@receiver(signal=periodic_task)
def clean_cached_files(sender, **kwargs):
    for cf in CachedFile.objects.filter(expires__isnull=False, expires__lt=now()):
        cf.delete()


@receiver(signal=periodic_task)
def clean_cached_tickets(sender, **kwargs):
    for cf in CachedTicket.objects.filter(created__lte=now() - timedelta(days=30)):
        cf.delete()
    for cf in CachedCombinedTicket.objects.filter(created__lte=now() - timedelta(days=30)):
        cf.delete()
