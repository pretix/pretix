import os

from django.core.files.base import ContentFile
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.i18n import language
from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, Order, OrderPosition,
)
from pretix.base.services.async import ProfiledTask
from pretix.base.signals import register_ticket_outputs
from pretix.celery_app import app
from pretix.helpers.database import rolledback_transaction


@app.task(base=ProfiledTask)
def generate(order_position: str, provider: str):
    order_position = OrderPosition.objects.select_related('order', 'order__event').get(id=order_position)
    try:
        ct = CachedTicket.objects.get(order_position=order_position, provider=provider)
    except CachedTicket.MultipleObjectsReturned:
        CachedTicket.objects.filter(order_position=order_position, provider=provider).delete()
        ct = CachedTicket.objects.create(order_position=order_position, provider=provider, extension='',
                                         type='', file=None)
    except CachedTicket.DoesNotExist:
        ct = CachedTicket.objects.create(order_position=order_position, provider=provider, extension='',
                                         type='', file=None)

    with language(order_position.order.locale):
        responses = register_ticket_outputs.send(order_position.order.event)
        for receiver, response in responses:
            prov = response(order_position.order.event)
            if prov.identifier == provider:
                filename, ct.type, data = prov.generate(order_position)
                path, ext = os.path.splitext(filename)
                ct.extension = ext
                ct.save()
                ct.file.save(filename, ContentFile(data))


@app.task(base=ProfiledTask)
def generate_order(order: int, provider: str):
    order = Order.objects.select_related('event').get(id=order)
    try:
        ct = CachedCombinedTicket.objects.get(order=order, provider=provider)
    except CachedCombinedTicket.MultipleObjectsReturned:
        CachedCombinedTicket.objects.filter(order=order, provider=provider).delete()
        ct = CachedCombinedTicket.objects.create(order=order, provider=provider, extension='',
                                                 type='', file=None)
    except CachedCombinedTicket.DoesNotExist:
        ct = CachedCombinedTicket.objects.create(order=order, provider=provider, extension='',
                                                 type='', file=None)

    with language(order.locale):
        responses = register_ticket_outputs.send(order.event)
        for receiver, response in responses:
            prov = response(order.event)
            if prov.identifier == provider:
                filename, ct.type, data = prov.generate_order(order)
                path, ext = os.path.splitext(filename)
                ct.extension = ext
                ct.save()
                ct.file.save(filename, ContentFile(data))


class DummyRollbackException(Exception):
    pass


def preview(event: int, provider: str):
    event = Event.objects.get(id=event)

    with rolledback_transaction(), language(event.settings.locale):
        item = event.items.create(name=_("Sample product"), default_price=42.23)

        order = event.orders.create(status=Order.STATUS_PENDING, datetime=now(),
                                    email='sample@pretix.eu',
                                    expires=now(), code="PREVIEW1234", total=119)

        p = order.positions.create(item=item, attendee_name=_("John Doe"), price=item.default_price)

        responses = register_ticket_outputs.send(event)
        for receiver, response in responses:
            prov = response(event)
            if prov.identifier == provider:
                return prov.generate(p)
