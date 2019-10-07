from django.db.models import Q
from django.dispatch import receiver

from pretix.base.models import Checkin
from pretix.base.signals import order_placed


@receiver(order_placed, dispatch_uid="autocheckin_order_placed")
def order_placed(sender, **kwargs):
    order = kwargs['order']
    event = sender

    cls = event.checkin_lists.filter(auto_checkin_sales_channels__contains=order.sales_channel)
    for op in order.positions.all():
        for cl in cls.filter(Q(all_products=True) | Q(limit_products=op.item)):
            Checkin.objects.create(position=op, list=cl, auto_checked_in=True)
