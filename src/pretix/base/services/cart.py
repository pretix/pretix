from datetime import timedelta

from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import (
    CartPosition, Event, EventLock, Item, ItemVariation, Quota,
)


class CartError(Exception):
    pass


error_messages = {
    'busy': _('We were not able to process your request completely as the '
              'server was too busy. Please try again.'),
    'empty': _('You did not select any items.'),
    'not_for_sale': _('You selected a product which is not available for sale.'),
    'unavailable': _('Some of the products you selected were no longer available. '
                     'Please see below for details.'),
    'in_part': _('Some of the products you selected were no longer available in '
                 'the quantity you selected. Please see below for details.'),
    'max_items': _("You cannot select more than %s items per order"),
    'not_started': _('The presale period for this event has not yet started.'),
    'ended': _('The presale period has ended.')
}


def _extend_existing(event, session, expiry):
    # Extend this user's cart session to 30 minutes from now to ensure all items in the
    # cart expire at the same time
    # We can extend the reservation of items which are not yet expired without risk
    CartPosition.objects.current.filter(
        Q(session=session) & Q(event=event) & Q(expires__gt=now())
    ).update(expires=expiry)


def _re_add_expired_positions(items, event, session):
    positions = set()
    # For items that are already expired, we have to delete and re-add them, as they might
    # be no longer available or prices might have changed. Sorry!
    expired = CartPosition.objects.current.filter(
        Q(session=session) & Q(event=event) & Q(expires__lte=now())
    )
    for cp in expired:
        items.insert(0, (cp.item_id, cp.variation_id, 1, cp))
        positions.add(cp)
    return positions


def _delete_expired(expired):
    for cp in expired:
        if cp.version_end_date is None:
            cp.delete()


def _check_date(event):
    if event.presale_start and now() < event.presale_start:
        raise CartError(error_messages['not_started'])
    if event.presale_end and now() > event.presale_end:
        raise CartError(error_messages['ended'])


def _add_items(event, items, session, expiry):
    err = None

    # Fetch items from the database
    items_query = Item.objects.current.filter(event=event, identity__in=[i[0] for i in items]).prefetch_related(
        "quotas")
    items_cache = {i.identity: i for i in items_query}
    variations_query = ItemVariation.objects.current.filter(
        item__event=event,
        identity__in=[i[1] for i in items if i[1] is not None]
    ).select_related("item", "item__event").prefetch_related("quotas", "values", "values__prop")
    variations_cache = {v.identity: v for v in variations_query}

    for i in items:
        # Check whether the specified items are part of what we just fetched from the database
        # If they are not, the user supplied item IDs which either do not exist or belong to
        # a different event
        if i[0] not in items_cache or (i[1] is not None and i[1] not in variations_cache):
            err = err or error_messages['not_for_sale']
            continue

        item = items_cache[i[0]]
        variation = variations_cache[i[1]] if i[1] is not None else None

        # Execute restriction plugins to check whether they (a) change the price or
        # (b) make the item/variation unavailable. If neither is the case, check_restriction
        # will correctly return the default price
        price = item.check_restrictions() if variation is None else variation.check_restrictions()

        # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.
        quotas = list(item.quotas.all()) if variation is None else list(variation.quotas.all())

        if price is False or len(quotas) == 0 or not item.active:
            err = err or error_messages['unavailable']
            continue

        # Assume that all quotas allow us to buy i[2] instances of the object
        quota_ok = i[2]
        for quota in quotas:
            avail = quota.availability()
            if avail[1] < i[2]:
                # This quota is not available or less than i[2] items are left, so we have to
                # reduce the number of bought items
                if avail[0] != Quota.AVAILABILITY_OK:
                    err = err or error_messages['unavailable']
                else:
                    err = err or error_messages['in_part']
                quota_ok = min(quota_ok, avail[1])

        # Create a CartPosition for as much items as we can
        for k in range(quota_ok):
            if len(i) > 3 and i[2] == 1:
                # Recreating
                cp = i[3].clone()
                cp.expires = expiry
                cp.price = price
                cp.save()
            else:
                CartPosition.objects.create(
                    event=event, item=item, variation=variation, price=price, expires=expiry,
                    session=session
                )
    return err


def add_items_to_cart(event: str, items: list, session: str=None):
    """
    Adds a list of items to a user's cart.
    :param event: The event ID in question
    :param items: A list of tuple of the form (item id, variation id or None, number)
    :param session: Session ID of a guest
    :raises CartError: On any error that occured
    """
    event = Event.objects.current.get(identity=event)
    try:
        with event.lock():
            _check_date(event)
            existing = CartPosition.objects.current.filter(Q(session=session) & Q(event=event)).count()
            if sum(i[2] for i in items) + existing > int(event.settings.max_items_per_order):
                # TODO: i18n plurals
                raise CartError(error_messages['max_items'] % event.settings.max_items_per_order)

            expiry = now() + timedelta(minutes=event.settings.get('reservation_time', as_type=int))
            _extend_existing(event, session, expiry)

            expired = _re_add_expired_positions(items, event, session)
            if not items:
                raise CartError(error_messages['empty'])

            err = _add_items(event, items, session, expiry)
            _delete_expired(expired)
            if err:
                raise CartError(err)
    except EventLock.LockTimeoutException:
        raise CartError(error_messages['busy'])


def remove_items_from_cart(event: str, items: list, session: str=None):
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param items: A list of tuple of the form (item id, variation id or None, number)
    :param session: Session ID of a guest
    """
    event = Event.objects.current.get(identity=event)

    for item, variation, cnt in items:
        cw = Q(session=session) & Q(item_id=item) & Q(event=event)
        if variation:
            cw &= Q(variation_id=variation)
        else:
            cw &= Q(variation__isnull=True)
        for cp in CartPosition.objects.current.filter(cw).order_by("-price")[:cnt]:
            cp.delete()
