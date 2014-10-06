from django.dispatch import receiver
from django.utils.timezone import now

from tixlbase.signals import determine_availability

from .models import TimeRestriction


@receiver(determine_availability)
def availability_handler(sender, **kwargs):
    # Handle the signal's input arguments
    item = kwargs['item']
    variations = kwargs['variations']
    cache = kwargs['cache']  # NOQA
    context = kwargs['context']  # NOQA

    # Fetch all restriction objects applied to this item
    restrictions = list(TimeRestriction.objects.filter(
        items__in=(item,),
    ).prefetch_related('variations'))

    # If we do not know anything about this item, we are done here.
    if len(restrictions) == 0:
        return variations

    # IMPORTANT:
    # We need to make a two-level deep copy of the variations list before we
    # modify it, becuase we need to to copy the dictionaries. Otherwise, we'll
    # interfere with other plugins.
    variations = [d.copy() for d in variations]

    # Walk through all variations we are asked for
    for v in variations:
        # If this point is reached, there ARE time restrictions for this item
        # Therefore, it is only available inside one of the timeframes, but not
        # without any timeframe
        available = False
        price = None
        # Walk through all restriction objects applied to this item
        for restriction in restrictions:
            applied_to = list(restriction.variations.all())

            # Only take this restriction into consideration if it either
            # is directly applied to this variation OR is applied to all
            # variations (e.g. the applied_to list is empty)
            if len(applied_to) > 0:
                if 'variation' not in v or v['variation'] not in applied_to:
                    continue

            if restriction.timeframe_from <= now() and restriction.timeframe_to >= now():
                # Selling this item is currently possible
                available = True
                # If multiple time frames are currently active, make sure to
                # get the cheapest price:
                if restriction.price is not None and (price is None or restriction.price < price):
                    price = restriction.price

        v['available'] = available
        v['price'] = price

    return variations
