import logging
import os
from datetime import timedelta

from django.core.files.base import ContentFile
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.i18n import language
from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, InvoiceAddress, Order,
    OrderPosition,
)
from pretix.base.services.tasks import ProfiledTask
from pretix.base.signals import allow_ticket_download, register_ticket_outputs
from pretix.celery_app import app
from pretix.helpers.database import rolledback_transaction

logger = logging.getLogger(__name__)


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
        item = event.items.create(name=_("Sample product"), default_price=42.23,
                                  description=_("Sample product description"))
        item2 = event.items.create(name=_("Sample workshop"), default_price=23.40)

        from pretix.base.models import Order
        order = event.orders.create(status=Order.STATUS_PENDING, datetime=now(),
                                    email='sample@pretix.eu',
                                    locale=event.settings.locale,
                                    expires=now(), code="PREVIEW1234", total=119)

        p = order.positions.create(item=item, attendee_name_parts={'full_name': _("John Doe")}, price=item.default_price)
        order.positions.create(item=item2, attendee_name_parts={'full_name': _("John Doe")}, price=item.default_price, addon_to=p)
        order.positions.create(item=item2, attendee_name_parts={'full_name': _("John Doe")}, price=item.default_price, addon_to=p)

        InvoiceAddress.objects.create(order=order, name_parts={'full_name': _("John Doe")}, company=_("Sample company"))

        responses = register_ticket_outputs.send(event)
        for receiver, response in responses:
            prov = response(event)
            if prov.identifier == provider:
                return prov.generate(p)


def get_cachedticket_for_position(pos, identifier, generate_async=True):
    apply_method = 'apply_async' if generate_async else 'apply'
    try:
        ct = CachedTicket.objects.filter(
            order_position=pos, provider=identifier
        ).last()
    except CachedTicket.DoesNotExist:
        ct = None

    if not ct:
        ct = CachedTicket.objects.create(
            order_position=pos, provider=identifier,
            extension='', type='', file=None)
        getattr(generate, apply_method)(args=(pos.id, identifier))
        if not generate_async:
            ct.refresh_from_db()

    if not ct.file:
        if now() - ct.created > timedelta(minutes=5):
            getattr(generate, apply_method)(args=(pos.id, identifier))
            if not generate_async:
                ct.refresh_from_db()
    return ct


def get_cachedticket_for_order(order, identifier, generate_async=True):
    apply_method = 'apply_async' if generate_async else 'apply'
    try:
        ct = CachedCombinedTicket.objects.filter(
            order=order, provider=identifier
        ).last()
    except CachedCombinedTicket.DoesNotExist:
        ct = None

    if not ct:
        ct = CachedCombinedTicket.objects.create(
            order=order, provider=identifier,
            extension='', type='', file=None)
        getattr(generate_order, apply_method)(args=(order.id, identifier))
        if not generate_async:
            ct.refresh_from_db()

    if not ct.file:
        if now() - ct.created > timedelta(minutes=5):
            getattr(generate_order, apply_method)(args=(order.id, identifier))
            if not generate_async:
                ct.refresh_from_db()
    return ct


def get_tickets_for_order(order):
    can_download = all([r for rr, r in allow_ticket_download.send(order.event, order=order)])
    if not can_download:
        return []
    if not order.ticket_download_available:
        return []

    providers = [
        response(order.event)
        for receiver, response
        in register_ticket_outputs.send(order.event)
    ]

    tickets = []

    for p in providers:
        if not p.is_enabled:
            continue

        if p.multi_download_enabled:
            try:
                ct = get_cachedticket_for_order(order, p.identifier, generate_async=False)
                tickets.append((
                    "{}-{}-{}{}".format(
                        order.event.slug.upper(), order.code, ct.provider, ct.extension,
                    ),
                    ct
                ))
            except:
                logger.exception('Failed to generate ticket.')
        else:
            for pos in order.positions.all():
                if pos.addon_to and not order.event.settings.ticket_download_addons:
                    continue
                if not pos.item.admission and not order.event.settings.ticket_download_nonadm:
                    continue
                try:
                    ct = get_cachedticket_for_position(pos, p.identifier, generate_async=False)
                    tickets.append((
                        "{}-{}-{}-{}{}".format(
                            order.event.slug.upper(), order.code, pos.positionid, ct.provider, ct.extension,
                        ),
                        ct
                    ))
                except:
                    logger.exception('Failed to generate ticket.')

    return tickets
