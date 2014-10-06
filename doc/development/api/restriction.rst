.. highlight:: python
   :linenothreshold: 5

Writing a restriction plugin
============================

Please make sure you have read and understood the :ref:`basic idea being tixl's restrictions 
<restrictionconcept>`. In this document, we will walk through the creation of a restriction
plugin using the example of a restriction by date and time.

Also, read :ref:`Creating a plugin <pluginsetup>` first.

The restriction model
---------------------

It is very likely that your new restriction plugin needs to store data. In order to do
so, it should define its own model with a name related to what your restriction does,
e.g. ``TimeRestriction``. This model should be a child class of ``tixlbase.models.BaseRestriction``.
You do not need to define custom fields, but you should create at least an empty model.
In our example, we put the following into :file:`tixlplugins/timerestriction/models.py`::

    from django.db import models
    from django.utils.translation import ugettext_lazy as _

    from tixlbase.models import BaseRestriction


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
restrict anything without doing so. It is available as ``tixlbase.signals.determine_availability``
and is sent out every time some component of tixl wants to know whether a specific item or
variation is available for sell.

It is sent out with several arguments:

    item
        The instance of ``tixlbase.models.Item`` in question.
    variations
        A list of dictionaries in the same format as ``Item.get_all_variations``: 
        The list contains one dictionary per variation, where the ``Property`` IDs are 
        keys and the ``PropertyValue`` objects are values. If an ``ItemVariation`` object 
        exists, it is available in the dictionary via the special key ``'variation'``. If
        the item does not have any properties, the list will contain exactly one empty
        dictionary. Please not: this is *not* the list of all possible variations, this is
        only the list of all variations the frontend likes to determine the status for.
    context
        A yet-to-defined context object containing information about the user and the order
        process. This is required to implement coupon-systems or similar restrictions.
    cache
        An object very similar to Django's own caching API (see tip below)

All receivers **have to** return a copy of the given list of variation dictionaries where each
dictionary can be extended by the following two keys:

    available
        A boolean value whether or not this plugin allows this variation to be on sale. Defaults
        to ``True``.
    price
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
    
    TBD

.. IMPORTANT::
    Please note the copying of the ``variations`` list in the example above.

.. _caching feature: https://docs.djangoproject.com/en/1.7/topics/cache/
