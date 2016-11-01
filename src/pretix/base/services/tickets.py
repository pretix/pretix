from datetime import timedelta

from django.core.files.base import ContentFile
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, CachedTicket, Event, Order, OrderPosition, cachedfile_name,
)
from pretix.base.signals import register_ticket_outputs
from pretix.celery import app
from pretix.helpers.database import rolledback_transaction


@app.task
def generate(order_position: str, provider: str):
    order_position = OrderPosition.objects.select_related('order', 'order__event').get(id=order_position)
    ct = CachedTicket.objects.get_or_create(order_position=order_position, provider=provider)[0]
    if not ct.cachedfile:
        cf = CachedFile()
        cf.date = now()
        cf.expires = order_position.order.event.date_from + timedelta(days=30)
        cf.save()
        ct.cachedfile = cf
        ct.save()

    with language(order_position.order.locale):
        responses = register_ticket_outputs.send(order_position.order.event)
        for receiver, response in responses:
            prov = response(order_position.order.event)
            if prov.identifier == provider:
                ct.cachedfile.filename, ct.cachedfile.type, data = prov.generate(order_position)
                ct.cachedfile.file.save(cachedfile_name(ct.cachedfile, ct.cachedfile.filename), ContentFile(data))
                ct.cachedfile.save()


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
