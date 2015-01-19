.. highlight:: python
   :linenothreshold: 5

Writing a restriction plugin
============================

Please make sure you have read and understood the :ref:`basic idea being pretix's restrictions 
<restrictionconcept>`. In this document, we will walk through the creation of a restriction
plugin using the example of a restriction by date and time.

Also, read :ref:`Creating a plugin <pluginsetup>` first.

The restriction model
---------------------

It is very likely that your new restriction plugin needs to store data. In order to do
so, it should define its own model with a name related to what your restriction does,
e.g. ``TimeRestriction``. This model should be a child class of ``pretixbase.models.BaseRestriction``.
You do not need to define custom fields, but you should create at least an empty model.
In our example, we put the following into :file:`pretixplugins/timerestriction/models.py`::

    from django.db import models
    from django.utils.translation import ugettext_lazy as _

    from pretixbase.models import BaseRestriction


    class TimeRestriction(BaseRestriction):
        """
        This restriction makes an item or variation only available
        within a given time frame. The price of the item can be modified
        during this time frame.
        """

        timeframe_from = models.DateTimeField(
            verbose_name=_("Start of time frame"),
        )
        timeframe_to = models.DateTimeField(
            verbose_name=_("End of time frame"),
        )
        price = models.DecimalField(
            null=True, blank=True,
            max_digits=7, decimal_places=2,
            verbose_name=_("Price in time frame"),
        )


The basic signals
-----------------

Availability determination
^^^^^^^^^^^^^^^^^^^^^^^^^^

This is the one signal *every* restriction plugin has to listen for, as your plugin does not
restrict anything without doing so. It is available as ``pretixbase.signals.determine_availability``
and is sent out every time some component of pretix wants to know whether a specific item or
variation is available for sell.

It is sent out with several keyword arguments:

    ``item``
        The instance of ``pretixbase.models.Item`` in question.
    ``variations``
        A list of dictionaries in the same format as ``Item.get_all_variations``: 
        The list contains one dictionary per variation, where the ``Property`` IDs are 
        keys and the ``PropertyValue`` objects are values. If an ``ItemVariation`` object 
        exists, it is available in the dictionary via the special key ``'variation'``. If
        the item does not have any properties, the list will contain exactly one empty
        dictionary. Please note: this is *not* the list of all possible variations, this is
        only the list of all variations the frontend likes to determine the status for.
        Technically, you won't get ``dict`` objects but ``pretixbase.types.VariationDict`` 
        objects, which behave exactly the same but add some extra methods.
    ``context``
        A yet-to-be-defined context object containing information about the user and the order
        process. This is required to implement coupon-systems or similar restrictions.
    ``cache``
        An object very similar to Django's own caching API (see tip below)

The positional argument ``sender`` contains the event.
All receivers **have to** return a copy of the given list of variation dictionaries where each
dictionary can be extended by the following two keys:

    ``available``
        A boolean value whether or not this plugin allows this variation to be on sale. Defaults
        to ``True``.
    ``price``
        A price to be set for this variation. Set to ``None`` or omit to keep the default price 
        of the variation or the item's base price.

.. IMPORTANT::
    As this signal might be called *a lot* under heavy load, you are expected to implement
    your receiver with an eye to performance. We highly recommend making use of Django's
    `caching feature`_. We cannot do this for you, as the possibility of caching highly
    depends on the details of your restriction. 
    
    **Attention:** Please use the **cache object provided in the signal** instead of importing
    it directly from django, so we can take care of invalidation whenever the organizer changes 
    the  event or item settings. Please also **prefix all your cache keys** with your
    plugin name.

In our example, the implementation could look like this::
    
    from django.dispatch import receiver
    from django.utils.timezone import now

    from pretixbase.signals import determine_availability

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

                # Only take this restriction into consideration if it
                # is directly applied to this variation or if the item
                # has no variations
                if len(v) != 0 and ('variation' not in v or v['variation'] not in applied_to):
                    continue

                if restriction.timeframe_from <= now() <= restriction.timeframe_to:
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

.. IMPORTANT::
    Please note the copying of the ``variations`` list in the example above (line 30).
    If you do not copy down to the ``dict`` objects, you will run into 
    interference problems with other plugins.

Control interface formsets
^^^^^^^^^^^^^^^^^^^^^^^^^^

To make it possible for the event organizer to configure your restriction, there is a
'Restrictions' page in the item configuration. This page is able to show a formset for
each restriction plugin, but *you* are required to create this formset. This is why you
should listen to the the ``pretixcontrol.signals.restriction_formset`` signal.

Currently, the signal comes with only one keyword argument:

    ``item``
        The instance of ``pretixbase.models.Item`` we want a formset for.

You are expected to return a dict containing the following items:

    ``formsetclass``
        An inline formset class (not a formset object).

    ``prefix``
        A unique prefix for your queryset.

    ``title``
        A title for your formset (normally your plugin name)

    ``description``
        An short, explanatory text about your restriction.


Our time restriction example looks like this::

    from django.utils.translation import ugettext_lazy as _
    from django.dispatch import receiver
    from django.forms.models import inlineformset_factory

    from pretixcontrol.signals import restriction_formset
    from pretixbase.models import Item
    from pretixcontrol.views.forms import (
        VariationsField, RestrictionInlineFormset, RestrictionForm
    )

    from .models import TimeRestriction

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
            'description': 'If you use this restriction type, the system will only '
                           'sell variations, which are covered by at least one of the '
                           'timeframes you define below.'
        }


.. NOTE::
   If you do use the ``RestrictionInlineFormset``, ``RestrictionForm`` and
   ``VariationsField`` classes in your implementation, we will do a lot of magic for you
   to display the ``variations`` field in the form in a nice and consistent way. So please,
   use these base classes and test carefully, if you make any changes to the behaviour
   of this field.
   

.. _caching feature: https://docs.djangoproject.com/en/1.7/topics/cache/
