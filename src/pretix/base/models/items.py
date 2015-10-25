import sys
from datetime import datetime
from decimal import Decimal
from itertools import product

from django.db import models
from django.db.models import Q, Case, Count, Sum, When
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from typing import List, Tuple, Union
from versions.models import VersionedForeignKey, VersionedManyToManyField

from pretix.base.i18n import I18nCharField, I18nTextField

from ..types import VariationDict
from .base import Versionable
from .event import Event


class ItemCategory(Versionable):
    """
    Items can be sorted into these categories.

    :param event: The event this belongs to
    :type event: Event
    :param name: The name of this category
    :type name: str
    :param position: An integer, used for sorting
    :type position: int
    """
    event = VersionedForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='categories',
    )
    name = I18nCharField(
        max_length=255,
        verbose_name=_("Category name"),
    )
    position = models.IntegerField(
        default=0
    )

    class Meta:
        verbose_name = _("Product category")
        verbose_name_plural = _("Product categories")
        ordering = ('position', 'version_birth_date')

    def __str__(self):
        return str(self.name)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    @property
    def sortkey(self):
        return self.position, self.version_birth_date

    def __lt__(self, other) -> bool:
        return self.sortkey < other.sortkey


def itempicture_upload_to(instance, filename: str) -> str:
    return '%s/%s/item-%s.%s' % (
        instance.event.organizer.slug, instance.event.slug, instance.identity,
        filename.split('.')[-1]
    )


class Item(Versionable):
    """
    An item is a thing which can be sold. It belongs to an event and may or may not belong to a category.
    Items are often also called 'products' but are named 'items' internally due to historic reasons.

    It has a default price which might by overriden by restrictions.

    :param event: The event this belongs to.
    :type event: Event
    :param category: The category this belongs to. May be null.
    :type category: ItemCategory
    :param name: The name of this item:
    :type name: str
    :param active: Whether this item is being sold
    :type active: bool
    :param description: A short description
    :type description: str
    :param default_price: The item's default price
    :type default_price: decimal.Decimal
    :param tax_rate: The VAT tax that is included in this item's price (in %)
    :type tax_rate: decimal.Decimal
    :param admission: ``True``, if this item allows persons to enter the event (as opposed to e.g. merchandise)
    :type admission: bool
    :param picture: A product picture to be shown next to the product description.
    :type picture: File

    """

    event = VersionedForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name=_("Event"),
    )
    category = VersionedForeignKey(
        ItemCategory,
        on_delete=models.PROTECT,
        related_name="items",
        blank=True, null=True,
        verbose_name=_("Category"),
    )
    name = I18nCharField(
        max_length=255,
        verbose_name=_("Item name"),
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    description = I18nTextField(
        verbose_name=_("Description"),
        help_text=_("This is shown below the product name in lists."),
        null=True, blank=True,
    )
    default_price = models.DecimalField(
        verbose_name=_("Default price"),
        max_digits=7, decimal_places=2, null=True
    )
    tax_rate = models.DecimalField(
        null=True, blank=True,
        verbose_name=_("Taxes included in percent"),
        max_digits=7, decimal_places=2
    )
    admission = models.BooleanField(
        verbose_name=_("Is an admission ticket"),
        help_text=_(
            'Whether or not buying this product allows a person to enter '
            'your event'
        ),
        default=False
    )
    position = models.IntegerField(
        default=0
    )
    picture = models.ImageField(
        verbose_name=_("Product picture"),
        null=True, blank=True,
        upload_to=itempicture_upload_to
    )

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ("category__position", "category", "position")

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def get_all_variations(self, use_cache: bool=False) -> List[VariationDict]:
        """
        This method returns a list containing all variations of this
        item. The list contains one VariationDict per variation, where
        the Proprty IDs are keys and the PropertyValue objects are
        values. If an ItemVariation object exists, it is available in
        the dictionary via the special key 'variation'.

        VariationDicts differ from dicts only by specifying some extra
        methods.

        :param use_cache: If this parameter is set to ``True``, a second call to this method
                          on the same model instance won't query the database again but return
                          the previous result again.
        :type use_cache: bool
        """
        if use_cache and hasattr(self, '_get_all_variations_cache'):
            return self._get_all_variations_cache

        all_variations = self.variations.all().prefetch_related("values")
        all_properties = self.properties.all().prefetch_related("values")
        variations_cache = {}
        for var in all_variations:
            key = []
            for v in var.values.all():
                key.append((v.prop_id, v.identity))
            key = tuple(sorted(key))
            variations_cache[key] = var

        result = []
        for comb in product(*[prop.values.all() for prop in all_properties]):
            if len(comb) == 0:
                result.append(VariationDict())
                continue
            key = []
            var = VariationDict()
            for v in comb:
                key.append((v.prop.identity, v.identity))
                var[v.prop.identity] = v
            key = tuple(sorted(key))
            if key in variations_cache:
                var['variation'] = variations_cache[key]
            result.append(var)

        self._get_all_variations_cache = result
        return result

    def _get_all_generated_variations(self):
        propids = set([p.identity for p in self.properties.all()])
        if len(propids) == 0:
            variations = [VariationDict()]
        else:
            all_variations = list(
                self.variations.annotate(
                    qc=Count('quotas')
                ).filter(qc__gt=0).prefetch_related(
                    "values", "values__prop", "quotas__event"
                )
            )
            variations = []
            for var in all_variations:
                values = list(var.values.all())
                # Make sure we don't expose stale ItemVariation objects which are
                # still around altough they have an old set of properties
                if set([v.prop.identity for v in values]) != propids:
                    continue
                vardict = VariationDict()
                for v in values:
                    vardict[v.prop.identity] = v
                vardict['variation'] = var
                variations.append(vardict)
        return variations

    def get_all_available_variations(self, use_cache: bool=False):
        """
        This method returns a list of all variations which are theoretically
        possible for sale. It DOES call all activated restriction plugins, and it
        DOES only return variations which DO have an ItemVariation object, as all
        variations without one CAN NOT be part of a Quota and therefore can never
        be available for sale. The only exception is the empty variation
        for items without properties, which never has an ItemVariation object.

        This DOES NOT take into account quotas itself. Use ``is_available`` on the
        ItemVariation objects (or the Item it self, if it does not have variations) to
        determine availability by the terms of quotas.

        It is recommended to call::

            .prefetch_related('properties', 'variations__values__prop')

        when retrieving Item objects you are going to use this method on.
        """
        if use_cache and hasattr(self, '_get_all_available_variations_cache'):
            return self._get_all_available_variations_cache

        from pretix.base.signals import determine_availability

        variations = self._get_all_generated_variations()
        responses = determine_availability.send(
            self.event, item=self,
            variations=variations, context=None,
            cache=self.event.get_cache()
        )

        for i, var in enumerate(variations):
            var['available'] = var['variation'].active if 'variation' in var else True
            if 'variation' in var:
                if var['variation'].default_price:
                    var['price'] = var['variation'].default_price
                else:
                    var['price'] = self.default_price
            else:
                var['price'] = self.default_price

            # It is possible, that *multiple* restriction plugins change the default price.
            # In this case, the cheapest one wins. As soon as there is a restriction
            # that changes the price, the default price has no effect.

            newprice = None
            for rec, response in responses:
                if 'available' in response[i] and not response[i]['available']:
                    var['available'] = False
                    break
                if 'price' in response[i] and response[i]['price'] is not None \
                        and (newprice is None or response[i]['price'] < newprice):
                    newprice = response[i]['price']
            var['price'] = newprice or var['price']

        variations = [var for var in variations if var['available']]

        self._get_all_available_variations_cache = variations
        return variations

    def check_quotas(self):
        """
        This method is used to determine whether this Item is currently available
        for sale.

        :returns: any of the return codes of :py:meth:`Quota.availability()`.

        :raises ValueError: if you call this on an item which has properties associated with it.
                            Please use the method on the ItemVariation object you are interested in.
        """
        if self.properties.count() > 0:  # NOQA
            raise ValueError('Do not call this directly on items which have properties '
                             'but call this on their ItemVariation objects')
        return min([q.availability() for q in self.quotas.all()],
                   key=lambda s: (s[0], s[1] if s[1] is not None else sys.maxsize))

    def check_restrictions(self):
        """
        This method is used to determine whether this ItemVariation is restricted
        in sale by any restriction plugins.

        :returns:

            * ``False``, if the item is unavailable
            * the item's price, otherwise

        :raises ValueError: if you call this on an item which has properties associated with it.
                            Please use the method on the ItemVariation object you are interested in.
        """
        if self.properties.count() > 0:  # NOQA
            raise ValueError('Do not call this directly on items which have properties '
                             'but call this on their ItemVariation objects')
        from pretix.base.signals import determine_availability

        vd = VariationDict()
        responses = determine_availability.send(
            self.event, item=self,
            variations=[vd], context=None,
            cache=self.event.get_cache()
        )
        price = self.default_price
        for rec, response in responses:
            if 'available' in response[0] and not response[0]['available']:
                return False
            elif 'price' in response[0] and response[0]['price'] is not None and response[0]['price'] < price:
                price = response[0]['price']
        return price


class Property(Versionable):
    """
    A property is a modifier which can be applied to an Item. For example
    'Size' would be a property associated with the item 'T-Shirt'.

    :param event: The event this belongs to
    :type event: Event
    :param name: The name of this property.
    :type name: str
    """

    event = VersionedForeignKey(
        Event,
        related_name="properties"
    )
    item = VersionedForeignKey(
        Item, related_name='properties', null=True, blank=True
    )
    name = I18nCharField(
        max_length=250,
        verbose_name=_("Property name")
    )

    class Meta:
        verbose_name = _("Product property")
        verbose_name_plural = _("Product properties")

    def __str__(self):
        return str(self.name)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()


class PropertyValue(Versionable):
    """
    A value of a property. If the property would be 'T-Shirt size',
    this could be 'M' or 'L'.

    :param prop: The property this value is a valid option for.
    :type prop: Property
    :param value: The value, as a human-readable string
    :type value: str
    :param position: An integer, used for sorting
    :type position: int
    """

    prop = VersionedForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="values"
    )
    value = I18nCharField(
        max_length=250,
        verbose_name=_("Value"),
    )
    position = models.IntegerField(
        default=0
    )

    class Meta:
        verbose_name = _("Property value")
        verbose_name_plural = _("Property values")
        ordering = ("position", "version_birth_date")

    def __str__(self):
        return "%s: %s" % (self.prop.name, self.value)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.prop:
            self.prop.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.prop:
            self.prop.event.get_cache().clear()

    @property
    def sortkey(self) -> Tuple[int, datetime]:
        return self.position, self.version_birth_date

    def __lt__(self, other) -> bool:
        return self.sortkey < other.sortkey


class ItemVariation(Versionable):
    """
    A variation is an item combined with values for all properties
    associated with the item. For example, if your item is 'T-Shirt'
    and your properties are 'Size' and 'Color', then an example for an
    variation would be 'T-Shirt XL read'.

    Attention: _ALL_ combinations of PropertyValues _ALWAYS_ exist,
    even if there is no ItemVariation object for them! ItemVariation objects
    do NOT prove existance, they are only available to make it possible
    to override default values (like the price) for certain combinations
    of property values. However, appropriate ItemVariation objects will be
    created as soon as you add your variations to a quota.

    They also allow to explicitly EXCLUDE certain combinations of property
    values by creating an ItemVariation object for them with active set to
    False.

    Restrictions can be not only set to items but also directly to variations.

    :param item: The item this variation belongs to
    :type item: Item
    :param values: A set of ``PropertyValue`` objects defining this variation
    :param active: Whether this value is to be sold.
    :type active: bool
    :param default_price: This variation's default price
    :type default_price: decimal.Decimal
    """
    item = VersionedForeignKey(
        Item,
        related_name='variations'
    )
    values = VersionedManyToManyField(
        PropertyValue,
        related_name='variations',
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    default_price = models.DecimalField(
        decimal_places=2, max_digits=7,
        null=True, blank=True,
        verbose_name=_("Default price"),
    )

    class Meta:
        verbose_name = _("Product variation")
        verbose_name_plural = _("Product variations")

    def __str__(self):
        return str(self.to_variation_dict())

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.item:
            self.item.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.item:
            self.item.event.get_cache().clear()

    def check_quotas(self) -> Tuple[int, int]:
        """
        This method is used to determine whether this ItemVariation is currently
        available for sale in terms of quotas.

        :returns: any of the return codes of :py:meth:`Quota.availability()`.
        """
        return min([q.availability() for q in self.quotas.all()],
                   key=lambda s: (s[0], s[1] if s[1] is not None else sys.maxsize))

    def to_variation_dict(self) -> VariationDict:
        """
        :return: a :py:class:`VariationDict` representing this variation.
        """
        vd = VariationDict()
        for v in self.values.all():
            vd[v.prop.identity] = v
        vd['variation'] = self
        return vd

    def check_restrictions(self) -> Union[bool, Decimal]:
        """
        This method is used to determine whether this ItemVariation is restricted
        in sale by any restriction plugins.

        :returns:

            * ``False``, if the item is unavailable
            * the item's price, otherwise
        """
        from pretix.base.signals import determine_availability

        responses = determine_availability.send(
            self.item.event, item=self.item,
            variations=[self.to_variation_dict()], context=None,
            cache=self.item.event.get_cache()
        )
        price = self.default_price if self.default_price is not None else self.item.default_price
        for rec, response in responses:
            if 'available' in response[0] and not response[0]['available']:
                return False
            elif 'price' in response[0] and response[0]['price'] is not None and response[0]['price'] < price:
                price = response[0]['price']
        return price

    def add_values_from_string(self, pk):
        """
        Add values to this ItemVariation using a serialized string of the form
        ``property-id:value-id,ṗroperty-id:value-id``
        """
        for pair in pk.split(","):
            prop, value = pair.split(":")
            self.values.add(
                PropertyValue.objects.current.get(
                    identity=value,
                    prop_id=prop
                )
            )


class VariationsField(VersionedManyToManyField):
    """
    This is a ManyToManyField using the pretixcontrol.views.forms.VariationsField
    form field by default.
    """

    def formfield(self, **kwargs):
        from pretix.control.forms import VariationsField as FVariationsField
        from django.db.models.fields.related import RelatedField

        defaults = {
            'form_class': FVariationsField,
            # We don't need a queryset
            'queryset': ItemVariation.objects.none(),
        }
        defaults.update(kwargs)
        # If initial is passed in, it's a list of related objects, but the
        # MultipleChoiceField takes a list of IDs.
        if defaults.get('initial') is not None:
            initial = defaults['initial']
            if callable(initial):
                initial = initial()
            defaults['initial'] = [i.identity for i in initial]
        # Skip ManyToManyField in dependency chain
        return super(RelatedField, self).formfield(**defaults)


class Question(Versionable):
    """
    A question is an input field that can be used to extend a ticket
    by custom information, e.g. "Attendee age". A question can allow one o several
    input types, currently:

    * a number (``TYPE_NUMBER``)
    * a one-line string (``TYPE_STRING``)
    * a multi-line string (``TYPE_TEXT``)
    * a boolean (``TYPE_BOOLEAN``)

    :param event: The event this question belongs to
    :type event: Event
    :param question: The question text. This will be displayed next to the input field.
    :type question: str
    :param type: One of the above types
    :param required: Whether answering this question is required for submiting an order including
                     items associated with this question.
    :type required: bool
    :param items: A set of ``Items`` objects that this question should be applied to
    """
    TYPE_NUMBER = "N"
    TYPE_STRING = "S"
    TYPE_TEXT = "T"
    TYPE_BOOLEAN = "B"
    TYPE_CHOICES = (
        (TYPE_NUMBER, _("Number")),
        (TYPE_STRING, _("Text (one line)")),
        (TYPE_TEXT, _("Multiline text")),
        (TYPE_BOOLEAN, _("Yes/No")),
    )

    event = VersionedForeignKey(
        Event,
        related_name="questions"
    )
    question = I18nTextField(
        verbose_name=_("Question")
    )
    type = models.CharField(
        max_length=5,
        choices=TYPE_CHOICES,
        verbose_name=_("Question type")
    )
    required = models.BooleanField(
        default=False,
        verbose_name=_("Required question")
    )
    items = VersionedManyToManyField(
        Item,
        related_name='questions',
        verbose_name=_("Products"),
        blank=True,
        help_text=_('This question will be asked to buyers of the selected products')
    )

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")

    def __str__(self):
        return str(self.question)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()


class BaseRestriction(Versionable):
    """
    A restriction is the abstract concept of a rule that limits the availability
    of Items or ItemVariations. This model is just an abstract base class to be
    extended by restriction plugins.
    """
    event = VersionedForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="restrictions_%(app_label)s_%(class)s",
        verbose_name=_("Event"),
    )
    item = VersionedForeignKey(
        Item,
        blank=True, null=True,
        verbose_name=_("Item"),
        related_name="restrictions_%(app_label)s_%(class)s",
    )
    variations = VariationsField(
        'pretixbase.ItemVariation',
        blank=True,
        verbose_name=_("Variations"),
        related_name="restrictions_%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True
        verbose_name = _("Restriction")
        verbose_name_plural = _("Restrictions")

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()


class Quota(Versionable):
    """
    A quota is a "pool of tickets". It is there to limit the number of items
    of a certain type to be sold. For example, you could have a quota of 500
    applied to all your items (because you only have that much space in your
    building), and also a quota of 100 applied to the VIP tickets for
    exclusivity. In this case, no more than 500 tickets will be sold in total
    and no more than 100 of them will be VIP tickets (but 450 normal and 50
    VIP tickets will be fine).

    As always, a quota can not only be tied to an item, but also to specific
    variations.

    Please read the documentation section on quotas carefully before doing
    anything with quotas. This might confuse you otherwise.
    http://docs.pretix.eu/en/latest/development/concepts.html#restriction-by-number

    The AVAILABILITY_* constants represent various states of an quota allowing
    its items/variations being for sale.

    AVAILABILITY_OK
        This item is available for sale.

    AVAILABILITY_RESERVED
        This item is currently not available for sale, because all available
        items are in people's shopping carts. It might become available
        again if those people do not proceed with checkout.

    AVAILABILITY_ORDERED
        This item is currently not availalbe for sale, because all available
        items are ordered. It might become available again if those people
        do not pay.

    AVAILABILITY_GONE
        This item is completely sold out.

    :param event: The event this belongs to
    :type event: Event
    :param name: This quota's name
    :type str:
    :param size: The number of items in this quota
    :type size: int
    :param items: The set of :py:class:`Item` objects this quota applies to
    :param variations: The set of :py:class:`ItemVariation` objects this quota applies to
    """

    AVAILABILITY_GONE = 0
    AVAILABILITY_ORDERED = 10
    AVAILABILITY_RESERVED = 20
    AVAILABILITY_OK = 100

    event = VersionedForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="quotas",
        verbose_name=_("Event"),
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name")
    )
    size = models.PositiveIntegerField(
        verbose_name=_("Total capacity"),
        null=True, blank=True,
        help_text=_("Leave empty for an unlimited number of tickets.")
    )
    items = VersionedManyToManyField(
        Item,
        verbose_name=_("Item"),
        related_name="quotas",
        blank=True
    )
    variations = VariationsField(
        ItemVariation,
        related_name="quotas",
        blank=True,
        verbose_name=_("Variations")
    )

    class Meta:
        verbose_name = _("Quota")
        verbose_name_plural = _("Quotas")

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()

    def availability(self) -> Tuple[int, int]:
        """
        This method is used to determine whether Items or ItemVariations belonging
        to this quota should currently be available for sale.

        :returns: a tuple where the first entry is one of the ``Quota.AVAILABILITY_`` constants
                  and the second is the number of available tickets.
        """
        size_left = self.size
        if size_left is None:
            return Quota.AVAILABILITY_OK, None

        # TODO: Test for interference with old versions of Item-Quota-relations, etc.
        # TODO: Prevent corner-cases like people having ordered an item before it got
        # its first variationsadde
        orders = self.count_orders()

        size_left -= orders['paid']
        if size_left <= 0:
            return Quota.AVAILABILITY_GONE, 0

        size_left -= orders['pending']
        if size_left <= 0:
            return Quota.AVAILABILITY_ORDERED, 0

        size_left -= self.count_in_cart()
        if size_left <= 0:
            return Quota.AVAILABILITY_RESERVED, 0

        return Quota.AVAILABILITY_OK, size_left

    def count_in_cart(self) -> int:
        from pretix.base.models import CartPosition

        return CartPosition.objects.current.filter(
            Q(expires__gte=now())
            & self._position_lookup
        ).count()

    def count_orders(self) -> dict:
        from pretix.base.models import Order, OrderPosition

        o = OrderPosition.objects.current.filter(self._position_lookup).aggregate(
            paid=Sum(
                Case(When(order__status=Order.STATUS_PAID, then=1),
                     output_field=models.IntegerField())
            ),
            pending=Sum(
                Case(When(Q(order__status=Order.STATUS_PENDING) & Q(order__expires__gte=now()), then=1),
                     output_field=models.IntegerField())
            )
        )
        for k, v in o.items():
            if v is None:
                o[k] = 0
        return o

    @cached_property
    def _position_lookup(self) -> Q:
        return (
            (  # Orders for items which do not have any variations
               Q(variation__isnull=True)
               & Q(item__quotas__in=[self])
            ) | (  # Orders for items which do have any variations
                   Q(variation__quotas__in=[self])
            )
        )

    class QuotaExceededException(Exception):
        pass
