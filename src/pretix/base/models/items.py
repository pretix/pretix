import sys
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Tuple

from django.conf import settings
from django.db import models
from django.db.models import F, Func, Q, Sum
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nCharField, I18nTextField

from pretix.base.decimal import round_decimal
from pretix.base.models.base import LoggedModel

from .event import Event


class ItemCategory(LoggedModel):
    """
    Items can be sorted into these categories.

    :param event: The event this category belongs to
    :type event: Event
    :param name: The name of this category
    :type name: str
    :param position: An integer, used for sorting
    :type position: int
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='categories',
    )
    name = I18nCharField(
        max_length=255,
        verbose_name=_("Category name"),
    )
    description = I18nTextField(
        blank=True, verbose_name=_("Category description")
    )
    position = models.IntegerField(
        default=0
    )

    class Meta:
        verbose_name = _("Product category")
        verbose_name_plural = _("Product categories")
        ordering = ('position', 'id')

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
        return self.position, self.id

    def __lt__(self, other) -> bool:
        return self.sortkey < other.sortkey


def itempicture_upload_to(instance, filename: str) -> str:
    return '%s/%s/item-%s-%s.%s' % (
        instance.event.organizer.slug, instance.event.slug, instance.id,
        str(uuid.uuid4()), filename.split('.')[-1]
    )


class Item(LoggedModel):
    """
    An item is a thing which can be sold. It belongs to an event and may or may not belong to a category.
    Items are often also called 'products' but are named 'items' internally due to historic reasons.

    :param event: The event this item belongs to
    :type event: Event
    :param category: The category this belongs to. May be null.
    :type category: ItemCategory
    :param name: The name of this item
    :type name: str
    :param active: Whether this item is being sold.
    :type active: bool
    :param description: A short description
    :type description: str
    :param default_price: The item's default price
    :type default_price: decimal.Decimal
    :param tax_rate: The VAT tax that is included in this item's price (in %)
    :type tax_rate: decimal.Decimal
    :param admission: ``True``, if this item allows persons to enter the event (as opposed to e.g. merchandise)
    :type admission: bool
    :param picture: A product picture to be shown next to the product description
    :type picture: File
    :param available_from: The date this product goes on sale
    :type available_from: datetime
    :param available_until: The date until when the product is on sale
    :type available_until: datetime
    :param require_voucher: If set to ``True``, this item can only be bought using a voucher.
    :type require_voucher: bool
    :param hide_without_voucher: If set to ``True``, this item is only visible and available when a voucher is used.
    :type hide_without_voucher: bool
    :param allow_cancel: If set to ``False``, an order with this product can not be canceled by the user.
    :type allow_cancel: bool
    """

    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name=_("Event"),
    )
    category = models.ForeignKey(
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
        help_text=_("If this product has multiple variations, you can set different prices for each of the "
                    "variations. If a variation does not have a special price or if you do not have variations, "
                    "this price will be used."),
        max_digits=7, decimal_places=2, null=True
    )
    free_price = models.BooleanField(
        default=False,
        verbose_name=_("Free price input"),
        help_text=_("If this option is active, your users can choose the price themselves. The price configured above "
                    "is then interpreted as the minimum price a user has to enter. You could use this e.g. to collect "
                    "additional donations for your event.")
    )
    tax_rate = models.DecimalField(
        verbose_name=_("Taxes included in percent"),
        max_digits=7, decimal_places=2,
        default=Decimal('0.00')
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
    available_from = models.DateTimeField(
        verbose_name=_("Available from"),
        null=True, blank=True,
        help_text=_('This product will not be sold before the given date.')
    )
    available_until = models.DateTimeField(
        verbose_name=_("Available until"),
        null=True, blank=True,
        help_text=_('This product will not be sold after the given date.')
    )
    require_voucher = models.BooleanField(
        verbose_name=_('This product can only be bought using a voucher.'),
        default=False,
        help_text=_('To buy this product, the user needs a voucher that applies to this product '
                    'either directly or via a quota.')
    )
    hide_without_voucher = models.BooleanField(
        verbose_name=_('This product will only be shown if a voucher matching the product is redeemed.'),
        default=False,
        help_text=_('This product will be hidden from the event page until the user enters a voucher '
                    'code that is specifically tied to this product (and not via a quota).')
    )
    allow_cancel = models.BooleanField(
        verbose_name=_('Allow product to be canceled'),
        default=True,
        help_text=_('If this is active and the general event settings allo wit, orders containing this product can be '
                    'canceled by the user until the order is paid for. Users cannot cancel paid orders on their own '
                    'and you can cancel orders at all times, regardless of this setting')
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

    @property
    def default_price_net(self):
        tax_value = round_decimal(self.default_price * (1 - 100 / (100 + self.tax_rate)))
        return self.default_price - tax_value

    def is_available(self, now_dt: datetime=None) -> bool:
        """
        Returns whether this item is available according to its ``active`` flag
        and its ``available_from`` and ``available_until`` fields
        """
        now_dt = now_dt or now()
        if not self.active:
            return False
        if self.available_from and self.available_from > now_dt:
            return False
        if self.available_until and self.available_until < now_dt:
            return False
        return True

    def check_quotas(self, ignored_quotas=None, count_waitinglist=True, _cache=None):
        """
        This method is used to determine whether this Item is currently available
        for sale.

        :param ignored_quotas: If a collection if quota objects is given here, those
                               quotas will be ignored in the calculation. If this leads
                               to no quotas being checked at all, this method will return
                               unlimited availability.
        :returns: any of the return codes of :py:meth:`Quota.availability()`.

        :raises ValueError: if you call this on an item which has variations associated with it.
                            Please use the method on the ItemVariation object you are interested in.
        """
        check_quotas = set(self.quotas.all())
        if ignored_quotas:
            check_quotas -= set(ignored_quotas)
        if not check_quotas:
            return Quota.AVAILABILITY_OK, sys.maxsize
        if self.variations.count() > 0:  # NOQA
            raise ValueError('Do not call this directly on items which have variations '
                             'but call this on their ItemVariation objects')
        return min([q.availability(count_waitinglist=count_waitinglist, _cache=_cache) for q in check_quotas],
                   key=lambda s: (s[0], s[1] if s[1] is not None else sys.maxsize))

    @cached_property
    def has_variations(self):
        return self.variations.exists()


class ItemVariation(models.Model):
    """
    A variation of a product. For example, if your item is 'T-Shirt'
    then an example for a variation would be 'T-Shirt XL'.

    :param item: The item this variation belongs to
    :type item: Item
    :param value: A string defining this variation
    :type value: str
    :param active: Whether this variation is being sold.
    :type active: bool
    :param default_price: This variation's default price
    :type default_price: decimal.Decimal
    """
    item = models.ForeignKey(
        Item,
        related_name='variations'
    )
    value = I18nCharField(
        max_length=255,
        verbose_name=_('Description')
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position")
    )
    default_price = models.DecimalField(
        decimal_places=2, max_digits=7,
        null=True, blank=True,
        verbose_name=_("Default price"),
    )

    class Meta:
        verbose_name = _("Product variation")
        verbose_name_plural = _("Product variations")
        ordering = ("position", "id")

    def __str__(self):
        return str(self.value)

    @property
    def price(self):
        return self.default_price if self.default_price is not None else self.item.default_price

    @property
    def net_price(self):
        tax_value = round_decimal(self.price * (1 - 100 / (100 + self.item.tax_rate)))
        return self.price - tax_value

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.item:
            self.item.event.get_cache().clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.item:
            self.item.event.get_cache().clear()

    def check_quotas(self, ignored_quotas=None, count_waitinglist=True, _cache=None) -> Tuple[int, int]:
        """
        This method is used to determine whether this ItemVariation is currently
        available for sale in terms of quotas.

        :param ignored_quotas: If a collection if quota objects is given here, those
                               quotas will be ignored in the calculation. If this leads
                               to no quotas being checked at all, this method will return
                               unlimited availability.
        :param count_waitinglist: If ``False``, waiting list entries will be ignored for quota calculation.
        :returns: any of the return codes of :py:meth:`Quota.availability()`.
        """
        check_quotas = set(self.quotas.all())
        if ignored_quotas:
            check_quotas -= set(ignored_quotas)
        if not check_quotas:
            return Quota.AVAILABILITY_OK, sys.maxsize
        return min([q.availability(count_waitinglist=count_waitinglist, _cache=_cache) for q in check_quotas],
                   key=lambda s: (s[0], s[1] if s[1] is not None else sys.maxsize))

    def __lt__(self, other):
        if self.position == other.position:
            return self.id < other.id
        return self.position < other.position


class Question(LoggedModel):
    """
    A question is an input field that can be used to extend a ticket by custom information,
    e.g. "Attendee age". The answers are found next to the position. The answers may be found
    in QuestionAnswers, attached to OrderPositions/CartPositions. A question can allow one of
    several input types, currently:

    * a number (``TYPE_NUMBER``)
    * a one-line string (``TYPE_STRING``)
    * a multi-line string (``TYPE_TEXT``)
    * a boolean (``TYPE_BOOLEAN``)
    * a multiple choice option (``TYPE_CHOICE`` and ``TYPE_CHOICE_MULTIPLE``)

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
    TYPE_CHOICE = "C"
    TYPE_CHOICE_MULTIPLE = "M"
    TYPE_CHOICES = (
        (TYPE_NUMBER, _("Number")),
        (TYPE_STRING, _("Text (one line)")),
        (TYPE_TEXT, _("Multiline text")),
        (TYPE_BOOLEAN, _("Yes/No")),
        (TYPE_CHOICE, _("Choose one from a list")),
        (TYPE_CHOICE_MULTIPLE, _("Choose multiple from a list"))
    )

    event = models.ForeignKey(
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
    items = models.ManyToManyField(
        Item,
        related_name='questions',
        verbose_name=_("Products"),
        blank=True,
        help_text=_('This question will be asked to buyers of the selected products')
    )
    position = models.IntegerField(
        default=0
    )

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")
        ordering = ('position', 'id')

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

    @property
    def sortkey(self):
        return self.position, self.id

    def __lt__(self, other) -> bool:
        return self.sortkey < other.sortkey


class QuestionOption(models.Model):
    question = models.ForeignKey('Question', related_name='options')
    answer = I18nCharField(verbose_name=_('Answer'))

    def __str__(self):
        return str(self.answer)


class Quota(LoggedModel):
    """
    A quota is a "pool of tickets". It is there to limit the number of items
    of a certain type to be sold. For example, you could have a quota of 500
    applied to all of your items (because you only have that much space in your
    venue), and also a quota of 100 applied to the VIP tickets for exclusivity.
    In this case, no more than 500 tickets will be sold in total and no more
    than 100 of them will be VIP tickets (but 450 normal and 50 VIP tickets
    will be fine).

    As always, a quota can not only be tied to an item, but also to specific
    variations.

    Please read the documentation section on quotas carefully before doing
    anything with quotas. This might confuse you otherwise.
    http://docs.pretix.eu/en/latest/development/concepts.html#restriction-by-number

    The AVAILABILITY_* constants represent various states of a quota allowing
    its items/variations to be up for sale.

    AVAILABILITY_OK
        This item is available for sale.

    AVAILABILITY_RESERVED
        This item is currently not available for sale because all available
        items are in people's shopping carts. It might become available
        again if those people do not proceed to the checkout.

    AVAILABILITY_ORDERED
        This item is currently not availalbe for sale because all available
        items are ordered. It might become available again if those people
        do not pay.

    AVAILABILITY_GONE
        This item is completely sold out.

    :param event: The event this belongs to
    :type event: Event
    :param name: This quota's name
    :type name: str
    :param size: The number of items in this quota
    :type size: int
    :param items: The set of :py:class:`Item` objects this quota applies to
    :param variations: The set of :py:class:`ItemVariation` objects this quota applies to
    """

    AVAILABILITY_GONE = 0
    AVAILABILITY_ORDERED = 10
    AVAILABILITY_RESERVED = 20
    AVAILABILITY_OK = 100

    event = models.ForeignKey(
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
    items = models.ManyToManyField(
        Item,
        verbose_name=_("Item"),
        related_name="quotas",
        blank=True
    )
    variations = models.ManyToManyField(
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

    def availability(self, now_dt: datetime=None, count_waitinglist=True, _cache=None) -> Tuple[int, int]:
        """
        This method is used to determine whether Items or ItemVariations belonging
        to this quota should currently be available for sale.

        :returns: a tuple where the first entry is one of the ``Quota.AVAILABILITY_`` constants
                  and the second is the number of available tickets.
        """
        if _cache and count_waitinglist is not _cache.get('_count_waitinglist', True):
            _cache.clear()

        if _cache is not None and self.pk in _cache:
            return _cache[self.pk]
        res = self._availability(now_dt, count_waitinglist)
        if _cache is not None:
            _cache[self.pk] = res
            _cache['_count_waitinglist'] = count_waitinglist
        return res

    def _availability(self, now_dt: datetime=None, count_waitinglist=True):
        now_dt = now_dt or now()
        size_left = self.size
        if size_left is None:
            return Quota.AVAILABILITY_OK, None

        # TODO: Test for interference with old versions of Item-Quota-relations, etc.
        size_left -= self.count_paid_orders()
        if size_left <= 0:
            return Quota.AVAILABILITY_GONE, 0

        size_left -= self.count_pending_orders()
        if size_left <= 0:
            return Quota.AVAILABILITY_ORDERED, 0

        size_left -= self.count_blocking_vouchers(now_dt)
        if size_left <= 0:
            return Quota.AVAILABILITY_ORDERED, 0

        size_left -= self.count_in_cart(now_dt)
        if size_left <= 0:
            return Quota.AVAILABILITY_RESERVED, 0

        if count_waitinglist:
            size_left -= self.count_waiting_list_pending()
            if size_left <= 0:
                return Quota.AVAILABILITY_RESERVED, 0

        return Quota.AVAILABILITY_OK, size_left

    def count_blocking_vouchers(self, now_dt: datetime=None) -> int:
        from pretix.base.models import Voucher

        now_dt = now_dt or now()
        if 'sqlite3' in settings.DATABASES['default']['ENGINE']:
            func = 'MAX'
        else:
            func = 'GREATEST'

        return Voucher.objects.filter(
            Q(block_quota=True) &
            Q(Q(valid_until__isnull=True) | Q(valid_until__gte=now_dt)) &
            Q(Q(self._position_lookup) | Q(quota=self))
        ).values('id').aggregate(
            free=Sum(Func(F('max_usages') - F('redeemed'), 0, function=func))
        )['free'] or 0

    def count_waiting_list_pending(self) -> int:
        from pretix.base.models import WaitingListEntry
        return WaitingListEntry.objects.filter(
            Q(voucher__isnull=True) &
            self._position_lookup
        ).distinct().count()

    def count_in_cart(self, now_dt: datetime=None) -> int:
        from pretix.base.models import CartPosition

        now_dt = now_dt or now()
        return CartPosition.objects.filter(
            Q(expires__gte=now_dt) &
            ~Q(
                Q(voucher__isnull=False) & Q(voucher__block_quota=True)
                & Q(Q(voucher__valid_until__isnull=True) | Q(voucher__valid_until__gte=now_dt))
            ) &
            self._position_lookup
        ).values('id').distinct().count()

    def count_pending_orders(self) -> dict:
        from pretix.base.models import Order, OrderPosition

        # This query has beeen benchmarked against a Count('id', distinct=True) aggregate and won by a small margin.
        return OrderPosition.objects.filter(
            self._position_lookup, order__status=Order.STATUS_PENDING,
        ).values('id').distinct().count()

    def count_paid_orders(self):
        from pretix.base.models import Order, OrderPosition

        return OrderPosition.objects.filter(
            self._position_lookup, order__status=Order.STATUS_PAID
        ).values('id').distinct().count()

    @cached_property
    def _position_lookup(self) -> Q:
        return (
            (  # Orders for items which do not have any variations
               Q(variation__isnull=True) &
               Q(item__quotas=self)
            ) | (  # Orders for items which do have any variations
                   Q(variation__quotas=self)
            )
        )

    class QuotaExceededException(Exception):
        pass
