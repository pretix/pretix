from django.dispatch import receiver
from django.forms.models import inlineformset_factory
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Item
from pretix.base.signals import determine_availability
from pretix.control.forms import RestrictionForm, RestrictionInlineFormset
from pretix.control.signals import restriction_formset

from .models import TimeRestriction


# The maximum validity of our cached values is the next date, one of our
# timeframe_from or tiemframe_to actions happens
def timediff(restrictions):
    for r in restrictions:
        if r.timeframe_from >= now():
            yield (r.timeframe_from - now()).total_seconds()
        if r.timeframe_to >= now():
            yield (r.timeframe_to - now()).total_seconds()


@receiver(determine_availability)
def availability_handler(sender, **kwargs):
    # Handle the signal's input arguments
    item = kwargs['item']
    variations = kwargs['variations']
    cache = kwargs['cache']
    context = kwargs['context']  # NOQA

    # Fetch all restriction objects applied to this item
    restrictions = list(TimeRestriction.objects.current.filter(
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

        # Make up some unique key for this variation
        cachekey = 'timerestriction:%s:%s' % (
            item.identity,
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
        prices = []
        for restriction in restrictions:
            applied_to = list(restriction.variations.current.all())

            # Only take this restriction into consideration if it
            # is directly applied to this variation or if the item
            # has no variations
            if not v.empty() and ('variation' not in v or v['variation'] not in applied_to):
                continue

            if restriction.timeframe_from <= now() <= restriction.timeframe_to:
                # Selling this item is currently possible
                available = True
                prices.append(restriction.price)

        # Use the lowest of all prices set by restrictions
        prices = [p for p in prices if p is not None]
        price = min(prices) if prices else None

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


class TimeRestrictionForm(RestrictionForm):

    class Meta:
        model = TimeRestriction
        localized_fields = '__all__'
        fields = [
            'variations',
            'timeframe_from',
            'timeframe_to',
            'price',
        ]


@receiver(restriction_formset)
def formset_handler(sender, **kwargs):
    formset = inlineformset_factory(
        Item,
        TimeRestriction,
        formset=RestrictionInlineFormset,
        form=TimeRestrictionForm,
        can_order=False,
        can_delete=True,
        extra=0,
    )

    return {
        'title': _('Restriction by time'),
        'formsetclass': formset,
        'prefix': 'timerestriction',
        'description': 'If you use this restriction type, the system will only sell variations which are covered '
                       'by at least one of the timeframes you define below. You can also change the price of '
                       'variations for within the given timeframe. Please note, that if you change the price of '
                       'variations here, this will overrule the price set in the "Variations" section.'
    }
