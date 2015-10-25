import random
import string
from datetime import datetime

from django.db import models
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from typing import List, Union
from versions.models import VersionedForeignKey

from .base import CachedFile, Versionable
from .event import Event
from .items import Item, ItemVariation, Question, Quota


def generate_secret():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))


class Order(Versionable):
    """
    An order is created when a user clicks 'buy' on his cart. It holds
    several OrderPositions and is connected to an user. It has an
    expiration date: If items run out of capacity, orders which are over
    their expiration date might be cancelled.

    An order -- like all objects -- has an ID, which is globally unique,
    but also a code, which is shorter and easier to memorize, but only
    unique among a single conference.

    :param code: In addition to the ID, which is globally unique, every
                 order has an order code, which is shorter and easier to
                 memorize, but is only unique among a single conference.
    :param status: The status of this order. One of:

        * ``STATUS_PENDING``
        * ``STATUS_PAID``
        * ``STATUS_EXPIRED``
        * ``STATUS_CANCELLED``
        * ``STATUS_REFUNDED``

    :param event: The event this belongs to
    :type event: Event
    :param email: The email of the person who ordered this
    :type email: str
    :param locale: The locale of this order
    :type locale: str
    :param datetime: The datetime of the order placement
    :type datetime: datetime
    :param expires: The date until this order has to be paid to guarantee the
    :type expires: datetime
    :param payment_date: The date of the payment completion (null, if not yet paid).
    :type payment_date: datetime
    :param payment_provider: The payment provider selected by the user
    :type payment_provider: str
    :param payment_fee: The payment fee calculated at checkout time
    :type payment_fee: decimal.Decimal
    :param payment_info: Arbitrary information stored by the payment provider
    :type payment_info: str
    :param total: The total amount of the order, including the payment fee
    :type total: decimal.Decimal
    """

    STATUS_PENDING = "n"
    STATUS_PAID = "p"
    STATUS_EXPIRED = "e"
    STATUS_CANCELLED = "c"
    STATUS_REFUNDED = "r"
    STATUS_CHOICE = (
        (STATUS_PENDING, _("pending")),
        (STATUS_PAID, _("paid")),
        (STATUS_EXPIRED, _("expired")),
        (STATUS_CANCELLED, _("cancelled")),
        (STATUS_REFUNDED, _("refunded"))
    )

    code = models.CharField(
        max_length=16,
        verbose_name=_("Order code")
    )
    status = models.CharField(
        max_length=3,
        choices=STATUS_CHOICE,
        verbose_name=_("Status")
    )
    event = VersionedForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="orders"
    )
    email = models.EmailField(
        null=True, blank=True,
        verbose_name=_('E-mail')
    )
    locale = models.CharField(
        null=True, blank=True, max_length=32,
        verbose_name=_('Locale')
    )
    secret = models.CharField(max_length=32, default=generate_secret)
    datetime = models.DateTimeField(
        verbose_name=_("Date")
    )
    expires = models.DateTimeField(
        verbose_name=_("Expiration date")
    )
    payment_date = models.DateTimeField(
        verbose_name=_("Payment date"),
        null=True, blank=True
    )
    payment_provider = models.CharField(
        null=True, blank=True,
        max_length=255,
        verbose_name=_("Payment provider")
    )
    payment_fee = models.DecimalField(
        decimal_places=2, max_digits=10,
        default=0, verbose_name=_("Payment method fee")
    )
    payment_info = models.TextField(
        verbose_name=_("Payment information"),
        null=True, blank=True
    )
    payment_manual = models.BooleanField(
        verbose_name=_("Payment state was manually modified"),
        default=False
    )
    total = models.DecimalField(
        decimal_places=2, max_digits=10,
        verbose_name=_("Total amount")
    )

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ("-datetime",)

    def __str__(self):
        return self.full_code

    @property
    def full_code(self):
        """
        A order code which is unique among all events of a single organizer,
        built by contatenating the event slug and the order code.
        """
        return self.event.slug.upper() + self.code

    def save(self, *args, **kwargs):
        if not self.code:
            self.assign_code()
        if not self.datetime:
            self.datetime = now()
        super().save(*args, **kwargs)

    def assign_code(self):
        charset = list('ABCDEFGHKLMNPQRSTUVWXYZ23456789')
        while True:
            code = "".join([random.choice(charset) for i in range(5)])
            if not Order.objects.filter(event=self.event, code=code).exists():
                self.code = code
                return

    @property
    def can_modify_answers(self) -> bool:
        """
        Is ``True`` if the user can change the question answers / attendee names that are
        related to the order. This checks order status and modification deadlines. It also
        returns ``False``, if there are no questions that can be answered.
        """
        if self.status not in (Order.STATUS_PENDING, Order.STATUS_PAID, Order.STATUS_EXPIRED):
            return False
        modify_deadline = self.event.settings.get('last_order_modification_date', as_type=datetime)
        if modify_deadline is not None and now() > modify_deadline:
            return False
        ask_names = self.event.settings.get('attendee_names_asked', as_type=bool)
        for cp in self.positions.all().prefetch_related('item__questions'):
            if (cp.item.admission and ask_names) or cp.item.questions.all():
                return True
        return False  # nothing there to modify

    def mark_refunded(self):
        """
        Mark this order as refunded. This clones the order object, sets the payment status and
        returns the cloned order object.
        """
        order = self.clone()
        order.status = Order.STATUS_REFUNDED
        order.save()
        return order

    def _can_be_paid(self) -> Union[bool, str]:
        error_messages = {
            'late': _("The payment is too late to be accepted."),
        }

        if self.event.settings.get('payment_term_last') \
                and now() > self.event.settings.get('payment_term_last'):
            return error_messages['late']
        if now() < self.expires:
            return True
        if not self.event.settings.get('payment_term_accept_late'):
            return error_messages['late']

        return self._is_still_available()

    def _is_still_available(self) -> Union[bool, str]:
        error_messages = {
            'unavailable': _('Some of the ordered products were no longer available.'),
        }
        positions = list(self.positions.all().select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation__values', 'variation__values__prop',
            'item__questions', 'answers'
        ))
        quota_cache = {}
        try:
            for i, op in enumerate(positions):
                quotas = list(op.item.quotas.all()) if op.variation is None else list(op.variation.quotas.all())
                if len(quotas) == 0:
                    raise Quota.QuotaExceededException(error_messages['unavailable'])

                for quota in quotas:
                    # Lock the quota, so no other thread is allowed to perform sales covered by this
                    # quota while we're doing so.
                    if quota.identity not in quota_cache:
                        quota_cache[quota.identity] = quota
                        quota.cached_availability = quota.availability()[1]
                    else:
                        # Use cached version
                        quota = quota_cache[quota.identity]
                    if quota.cached_availability is not None:
                        quota.cached_availability -= 1
                        if quota.cached_availability < 0:
                            # This quota is sold out/currently unavailable, so do not sell this at all
                            raise Quota.QuotaExceededException(error_messages['unavailable'])
        except Quota.QuotaExceededException as e:
            return str(e)
        return True


class CachedTicket(models.Model):
    order = VersionedForeignKey(Order, on_delete=models.CASCADE)
    cachedfile = models.ForeignKey(CachedFile, on_delete=models.CASCADE)
    provider = models.CharField(max_length=255)


class QuestionAnswer(Versionable):
    """
    The answer to a Question, connected to an OrderPosition or CartPosition.

    :param orderposition: The order position this is related to, or null if this is
                          related to a cart position.
    :type orderposition: OrderPosition
    :param cartposition: The cart position this is related to, or null if this is related
                         to an order position.
    :type cartposition: CartPosition
    :param question: The question this is an answer for
    :type question: Question
    :param answer: The actual answer data
    :type answer: str
    """
    orderposition = models.ForeignKey(
        'OrderPosition', null=True, blank=True,
        related_name='answers'
    )
    cartposition = models.ForeignKey(
        'CartPosition', null=True, blank=True,
        related_name='answers'
    )
    question = VersionedForeignKey(
        Question, related_name='answers'
    )
    answer = models.TextField()


class ObjectWithAnswers:
    def cache_answers(self):
        """
        Creates two properties on the object.
        (1) answ: a dictionary of question.id → answer string
        (2) questions: a list of Question objects, extended by an 'answer' property
        """
        self.answ = {}
        for a in self.answers.all():
            self.answ[a.question_id] = a.answer
        self.questions = []
        for q in self.item.questions.all():
            if q.identity in self.answ:
                q.answer = self.answ[q.identity]
            else:
                q.answer = ""
            self.questions.append(q)


class OrderPosition(ObjectWithAnswers, Versionable):
    """
    An OrderPosition is one line of an order, representing one ordered items
    of a specified type (or variation).

    :param order: The order this is a part of
    :type order: Order
    :param item: The ordered item
    :type item: Item
    :param variation: The ordered ItemVariation or null, if the item has no properties
    :type variation: ItemVariation
    :param price: The price of this item
    :type price: decimal.Decimal
    :param attendee_name: The attendee's name, if entered.
    :type attendee_name: str
    """
    order = VersionedForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='positions'
    )
    item = VersionedForeignKey(
        Item,
        verbose_name=_("Item"),
        related_name='positions'
    )
    variation = VersionedForeignKey(
        ItemVariation,
        null=True, blank=True,
        verbose_name=_("Variation")
    )
    price = models.DecimalField(
        decimal_places=2, max_digits=10,
        verbose_name=_("Price")
    )
    attendee_name = models.CharField(
        max_length=255,
        verbose_name=_("Attendee name"),
        blank=True, null=True,
        help_text=_("Empty, if this product is not an admission ticket")
    )

    class Meta:
        verbose_name = _("Order position")
        verbose_name_plural = _("Order positions")

    @classmethod
    def transform_cart_positions(cls, cp: List, order) -> list:
        ops = []
        for cartpos in cp:
            op = OrderPosition(
                order=order, item=cartpos.item, variation=cartpos.variation,
                price=cartpos.price, attendee_name=cartpos.attendee_name
            )
            for answ in cartpos.answers.all():
                answ = answ.clone()
                answ.orderposition = op
                answ.cartposition = None
                answ.save()
            op.save()
            cartpos.delete()
            ops.append(op)


class CartPosition(ObjectWithAnswers, Versionable):
    """
    A cart position is similar to a order line, except that it is not
    yet part of a binding order but just placed by some user in his or
    her cart. It therefore normally has a much shorter expiration time
    than an ordered position, but still blocks an item in the quota pool
    as we do not want to throw out users while they're clicking through
    the checkout process.

    :param event: The event this belongs to
    :type event: Evnt
    :param item: The selected item
    :type item: Item
    :param cart_id: The user session that contains this cart position
    :type cart_id: str
    :param variation: The selected ItemVariation or null, if the item has no properties
    :type variation: ItemVariation
    :param datetime: The datetime this item was put into the cart
    :type datetime: datetime
    :param expires: The date until this item is guarenteed to be reserved
    :type expires: datetime
    :param price: The price of this item
    :type price: decimal.Decimal
    :param attendee_name: The attendee's name, if entered.
    :type attendee_name: str
    """
    event = VersionedForeignKey(
        Event,
        verbose_name=_("Event")
    )
    cart_id = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name=_("Cart ID (e.g. session key)")
    )
    item = VersionedForeignKey(
        Item,
        verbose_name=_("Item")
    )
    variation = VersionedForeignKey(
        ItemVariation,
        null=True, blank=True,
        verbose_name=_("Variation")
    )
    price = models.DecimalField(
        decimal_places=2, max_digits=10,
        verbose_name=_("Price")
    )
    datetime = models.DateTimeField(
        verbose_name=_("Date"),
        auto_now_add=True
    )
    expires = models.DateTimeField(
        verbose_name=_("Expiration date")
    )
    attendee_name = models.CharField(
        max_length=255,
        verbose_name=_("Attendee name"),
        blank=True, null=True,
        help_text=_("Empty, if this product is not an admission ticket")
    )

    class Meta:
        verbose_name = _("Cart position")
        verbose_name_plural = _("Cart positions")
