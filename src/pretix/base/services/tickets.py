import logging
import os

from django.core.files.base import ContentFile
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_scopes import scopes_disabled

from pretix.base.i18n import language
from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, InvoiceAddress, Order,
    OrderPosition,
)
from pretix.base.services.tasks import EventTask, ProfiledTask
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import allow_ticket_download, register_ticket_outputs
from pretix.celery_app import app
from pretix.helpers.database import rolledback_transaction

logger = logging.getLogger(__name__)


def generate_orderposition(order_position: int, provider: str):
    order_position = OrderPosition.objects.select_related('order', 'order__event').get(id=order_position)

    with language(order_position.order.locale):
        responses = register_ticket_outputs.send(order_position.order.event)
        for receiver, response in responses:
            prov = response(order_position.order.event)
            if prov.identifier == provider:
                filename, ttype, data = prov.generate(order_position)
                path, ext = os.path.splitext(filename)
                for ct in CachedTicket.objects.filter(order_position=order_position, provider=provider):
                    ct.delete()
                ct = CachedTicket.objects.create(order_position=order_position, provider=provider,
                                                 extension=ext, type=ttype, file=None)
                ct.file.save(filename, ContentFile(data))
                return ct.pk


def generate_order(order: int, provider: str):
    order = Order.objects.select_related('event').get(id=order)

    with language(order.locale):
        responses = register_ticket_outputs.send(order.event)
        for receiver, response in responses:
            prov = response(order.event)
            if prov.identifier == provider:
                filename, ttype, data = prov.generate_order(order)
                if ttype == 'text/uri-list':
                    continue

                path, ext = os.path.splitext(filename)
                for ct in CachedCombinedTicket.objects.filter(order=order, provider=provider):
                    ct.delete()
                ct = CachedCombinedTicket.objects.create(order=order, provider=provider, extension=ext,
                                                         type=ttype, file=None)
                ct.file.save(filename, ContentFile(data))
                return ct.pk


@app.task(base=ProfiledTask)
def generate(model: str, pk: int, provider: str):
    with scopes_disabled():
        if model == 'order':
            return generate_order(pk, provider)
        elif model == 'orderposition':
            return generate_orderposition(pk, provider)


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

        scheme = PERSON_NAME_SCHEMES[event.settings.name_scheme]
        sample = {k: str(v) for k, v in scheme['sample'].items()}
        p = order.positions.create(item=item, attendee_name_parts=sample, price=item.default_price)
        s = event.subevents.first()
        order.positions.create(item=item2, attendee_name_parts=sample, price=item.default_price, addon_to=p, subevent=s)
        order.positions.create(item=item2, attendee_name_parts=sample, price=item.default_price, addon_to=p, subevent=s)

        InvoiceAddress.objects.create(order=order, name_parts=sample, company=_("Sample company"))

        responses = register_ticket_outputs.send(event)
        for receiver, response in responses:
            prov = response(event)
            if prov.identifier == provider:
                return prov.generate(p)


def get_tickets_for_order(order, base_position=None):
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

    positions = list(order.positions_with_tickets)
    if base_position:
        # Only the given position and its children
        positions = [
            p for p in positions if p.pk == base_position.pk or p.addon_to_id == base_position.pk
        ]

    for p in providers:
        if not p.is_enabled:
            continue

        if p.multi_download_enabled and not base_position:
            try:
                if len(positions) == 0:
                    continue
                ct = CachedCombinedTicket.objects.filter(
                    order=order, provider=p.identifier, file__isnull=False
                ).last()
                if not ct or not ct.file:
                    retval = generate_order(order.pk, p.identifier)
                    if not retval:
                        continue
                    ct = CachedCombinedTicket.objects.get(pk=retval)
                tickets.append((
                    "{}-{}-{}{}".format(
                        order.event.slug.upper(), order.code, ct.provider, ct.extension,
                    ),
                    ct
                ))
            except:
                logger.exception('Failed to generate ticket.')
        else:
            for pos in positions:
                try:
                    ct = CachedTicket.objects.filter(
                        order_position=pos, provider=p.identifier, file__isnull=False
                    ).last()
                    if not ct or not ct.file:
                        retval = generate_orderposition(pos.pk, p.identifier)
                        if not retval:
                            continue
                        ct = CachedTicket.objects.get(pk=retval)

                    if ct.type == 'text/uri-list':
                        continue

                    tickets.append((
                        "{}-{}-{}-{}{}".format(
                            order.event.slug.upper(), order.code, pos.positionid, ct.provider, ct.extension,
                        ),
                        ct
                    ))
                except:
                    logger.exception('Failed to generate ticket.')

    return tickets


@app.task(base=EventTask, acks_late=True)
def invalidate_cache(event: Event, item: int=None, provider: str=None, order: int=None, **kwargs):
    qs = CachedTicket.objects.filter(order_position__order__event=event)
    qsc = CachedCombinedTicket.objects.filter(order__event=event)

    if item:
        qs = qs.filter(order_position__item_id=item)

    if provider:
        qs = qs.filter(provider=provider)
        qsc = qsc.filter(provider=provider)

    if order:
        qs = qs.filter(order_position__order_id=order)
        qsc = qsc.filter(order_id=order)

    for ct in qs:
        ct.delete()
    for ct in qsc:
        ct.delete()
