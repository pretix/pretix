from django.dispatch import receiver
from django.utils.timezone import now

from tixlbase.signals import determine_availability

from .models import TimeRestriction


@receiver(determine_availability)
def availability_handler(sender, **kwargs):
    # Handle the signal's input arguments
    item = kwargs['item']
    variations = kwargs['variations']
    cache = kwargs['cache']
    context = kwargs['context']  # NOQA

    # Fetch all restriction objects applied to this item
    restrictions = list(TimeRestriction.objects.filter(
        item=item,
    ).prefetch_related('variations'))

    # If we do not know anything about this item, we are done here.
    if len(restrictions) == 0:
        return variations

    # IMPORTANT:
    # We need to make a two-level deep copy of the variations list before we
    # modify it, becuase we need to to copy the dictionaries. Otherwise, we'll
    # interfere with other plugins.
    variations = [d.copy() for d in variations]

    # The maximum validity of our cached values is the next date, one of our
    # timeframe_from or tiemframe_to actions happens
    def timediff(restrictions):
        for r in restrictions:
            if r.timeframe_from >= now():
                yield (r.timeframe_from - now()).total_seconds()
            if r.timeframe_to >= now():
                yield (r.timeframe_to - now()).total_seconds()

    try:
        cache_validity = min(timediff(restrictions))
    except ValueError:
        # empty sequence
        # If we get here, there are restrictions available but nothing will
        # change about them any more. If it were not for the case of no
        # restriction for the base item but restrictions for special
        # variations, we could quit here with 'item not available'.
        cache_validity = 3600

    # Walk through all variations we are asked for
    for v in variations:
        # If this point is reached, there ARE time restrictions for this item
        # Therefore, it is only available inside one of the timeframes, but not
        # without any timeframe
        available = False
        price = None

        # Make up some unique key for this variation
        cachekey = 'timerestriction:%d:%s' % (
            item.pk,
            v.identify(),
        )

        # Fetch from cache, if available
        cached = cache.get(cachekey)
        if cached is not None:
            v['available'] = (cached.split(":")[0] == 'True')
            try:
                v['price'] = float(cached.split(":")[1])
            except ValueError:
                v['price'] = None
            continue

        # Walk through all restriction objects applied to this item
        for restriction in restrictions:
            applied_to = list(restriction.variations.all())

            # Only take this restriction into consideration if it either
            # is directly applied to this variation OR is applied to all
            # variations (e.g. the applied_to list is empty)
            if len(applied_to) > 0:
                if 'variation' not in v or v['variation'] not in applied_to:
                    continue

            if (restriction.timeframe_from <= now()
                    and restriction.timeframe_to >= now()):
                # Selling this item is currently possible
                available = True
                # If multiple time frames are currently active, make sure to
                # get the cheapest price:
                if (restriction.price is not None
                        and (price is None or restriction.price < price)):
                    price = restriction.price

        v['available'] = available
        v['price'] = price
        cache.set(
            cachekey,
            '%s:%s' % (
                'True' if available else 'False',
                str(price) if price else ''
            ),
            cache_validity
        )

    return variations
