import copy
import random
import string
from datetime import datetime
from decimal import Decimal
from typing import List, Union

from django.conf import settings
from django.db import models
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from ..decimal import round_decimal
from .base import CachedFile, LoggedModel
from .event import Event
from .items import Item, ItemVariation, Question, QuestionOption, Quota


def generate_secret():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))


def generate_position_secret():
    # Exclude o,0,1,i,l to avoid confusion with bad fonts/printers
    return ''.join(random.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(settings.ENTROPY['ticket_secret']))


class Order(LoggedModel):
    """
    An order is created when a user clicks 'buy' on his cart. It holds
    several OrderPositions and is connected to a user. It has an
    expiration date: If items run out of capacity, orders which are over
    their expiration date might be cancelled.

    An order -- like all objects -- has an ID, which is globally unique,
    but also a code, which is shorter and easier to memorize, but only
    unique within a single conference.

    :param code: In addition to the ID, which is globally unique, every
                 order has an order code, which is shorter and easier to
                 memorize, but is only unique within a single conference.
    :type code: str
    :param status: The status of this order. One of:

        * ``STATUS_PENDING``
        * ``STATUS_PAID``
        * ``STATUS_EXPIRED``
        * ``STATUS_CANCELLED``
        * ``STATUS_REFUNDED``

    :param event: The event this order belongs to
    :type event: Event
    :param email: The email of the person who ordered this
    :type email: str
    :param locale: The locale of this order
    :type locale: str
    :param secret: A secret string that is required to modify the order
    :type secret: str
    :param datetime: The datetime of the order placement
    :type datetime: datetime
    :param expires: The date until this order has to be paid to guarantee the fulfillment
    :type expires: datetime
    :param payment_date: The date of the payment completion (null if not yet paid)
    :type payment_date: datetime
    :param payment_provider: The payment provider selected by the user
    :type payment_provider: str
    :param payment_fee: The payment fee calculated at checkout time
    :type payment_fee: decimal.Decimal
    :param payment_fee_tax_value: The absolute amount of tax included in the payment fee
    :type payment_fee_tax_value: decimal.Decimal
    :param payment_fee_tax_rate: The tax rate applied to the payment fee (in percent)
    :type payment_fee_tax_rate: decimal.Decimal
    :param payment_info: Arbitrary information stored by the payment provider
    :type payment_info: str
    :param total: The total amount of the order, including the payment fee
    :type total: decimal.Decimal
    :param comment: An internal comment that will only be visible to staff, and never displayed to the user
    :type comment: str
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
        verbose_name=_("Order code"),
        db_index=True
    )
    status = models.CharField(
        max_length=3,
        choices=STATUS_CHOICE,
        verbose_name=_("Status"),
        db_index=True
    )
    event = models.ForeignKey(
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
    payment_fee_tax_rate = models.DecimalField(
        decimal_places=2, max_digits=10,
        verbose_name=_("Payment method fee tax rate")
    )
    payment_fee_tax_value = models.DecimalField(
        decimal_places=2, max_digits=10,
        default=0, verbose_name=_("Payment method fee tax")
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
    comment = models.TextField(
        blank=True, verbose_name=_("Comment"),
        help_text=_("The text entered in this field will not be visible to the user and is available for your "
                    "convenience.")
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
        An order code which is unique among all events of a single organizer,
        built by contatenating the event slug and the order code.
        """
        return self.event.slug.upper() + self.code

    def save(self, *args, **kwargs):
        if not self.code:
            self.assign_code()
        if not self.datetime:
            self.datetime = now()
        if self.payment_fee_tax_rate is None:
            self._calculate_tax()
        super().save(*args, **kwargs)

    def _calculate_tax(self):
        """
        Calculates the taxes on the payment fees and sets the parameters payment_fee_tax_rate
        and payment_fee_tax_value accordingly.
        """
        self.payment_fee_tax_rate = self.event.settings.get('tax_rate_default')
        if self.payment_fee_tax_rate:
            self.payment_fee_tax_value = round_decimal(
                self.payment_fee * (1 - 100 / (100 + self.payment_fee_tax_rate)))
        else:
            self.payment_fee_tax_value = Decimal('0.00')

    def assign_code(self):
        charset = list('ABCDEFGHKLMNPQRSTUVWXYZ23456789')
        while True:
            code = "".join([random.choice(charset) for i in range(settings.ENTROPY['order_code'])])
            if not Order.objects.filter(event=self.event, code=code).exists():
                self.code = code
                return

    @property
    def can_modify_answers(self) -> bool:
        """
        ``True`` if the user can change the question answers / attendee names that are
        related to the order. This checks order status and modification deadlines. It also
        returns ``False`` if there are no questions that can be answered.
        """
        if self.status not in (Order.STATUS_PENDING, Order.STATUS_PAID, Order.STATUS_EXPIRED):
            return False
        modify_deadline = self.event.settings.get('last_order_modification_date', as_type=datetime)
        if modify_deadline is not None and now() > modify_deadline:
            return False
        if self.event.settings.get('invoice_address_asked', as_type=bool):
            return True
        ask_names = self.event.settings.get('attendee_names_asked', as_type=bool)
        for cp in self.positions.all().prefetch_related('item__questions'):
            if (cp.item.admission and ask_names) or cp.item.questions.all():
                return True

        return False  # nothing there to modify

    @property
    def is_expired_by_time(self):
        return (
            self.status == Order.STATUS_PENDING and self.expires < now()
            and not self.event.settings.get('payment_term_expire_automatically')
        )

    def _can_be_paid(self) -> Union[bool, str]:
        error_messages = {
            'late': _("The payment is too late to be accepted."),
        }

        if self.event.settings.get('payment_term_last') \
                and now() > self.event.settings.get('payment_term_last'):
            return error_messages['late']
        if self.status == self.STATUS_PENDING:
            return True
        if not self.event.settings.get('payment_term_accept_late'):
            return error_messages['late']

        return self._is_still_available()

    def _is_still_available(self) -> Union[bool, str]:
        error_messages = {
            'unavailable': _('Some of the ordered products are no longer available.'),
        }
        positions = self.positions.all().select_related('item', 'variation')
        quota_cache = {}
        try:
            for i, op in enumerate(positions):
                quotas = list(op.item.quotas.all()) if op.variation is None else list(op.variation.quotas.all())
                if len(quotas) == 0:
                    raise Quota.QuotaExceededException(error_messages['unavailable'])

                for quota in quotas:
                    # Lock the quota, so no other thread is allowed to perform sales covered by this
                    # quota while we're doing so.
                    if quota.id not in quota_cache:
                        quota_cache[quota.id] = quota
                        quota.cached_availability = quota.availability()[1]
                    else:
                        # Use cached version
                        quota = quota_cache[quota.id]
                    if quota.cached_availability is not None:
                        quota.cached_availability -= 1
                        if quota.cached_availability < 0:
                            # This quota is sold out/currently unavailable, so do not sell this at all
                            raise Quota.QuotaExceededException(error_messages['unavailable'])
        except Quota.QuotaExceededException as e:
            return str(e)
        return True


class CachedTicket(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    cachedfile = models.ForeignKey(CachedFile, on_delete=models.CASCADE)
    provider = models.CharField(max_length=255)


class QuestionAnswer(models.Model):
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
    question = models.ForeignKey(
        Question, related_name='answers'
    )
    options = models.ManyToManyField(
        QuestionOption, related_name='answers', blank=True
    )
    answer = models.TextField()

    def __str__(self):
        if self.question.type == Question.TYPE_BOOLEAN and self.answer == "True":
            return str(_("Yes"))
        elif self.question.type == Question.TYPE_BOOLEAN and self.answer == "False":
            return str(_("No"))
        else:
            return self.answer

    def save(self, *args, **kwargs):
        if self.orderposition and self.cartposition:
            raise ValueError('QuestionAnswer cannot be linked to an order and a cart position at the same time.')
        super().save(*args, **kwargs)


class AbstractPosition(models.Model):
    """
    A position can either be one line of an order or an item placed in a cart.

    :param item: The selected item
    :type item: Item
    :param variation: The selected ItemVariation or null, if the item has no variations
    :type variation: ItemVariation
    :param datetime: The datetime this item was put into the cart
    :type datetime: datetime
    :param expires: The date until this item is guarenteed to be reserved
    :type expires: datetime
    :param price: The price of this item
    :type price: decimal.Decimal
    :param attendee_name: The attendee's name, if entered.
    :type attendee_name: str
    :param voucher: A voucher that has been applied to this sale
    :type voucher: Voucher
    :param voucher_discount: The absolute discount granted by the applied voucher
    :type voucher_discount: decimal.Decimal
    :param base_price: The base price without any discounts applied
    :type base_price: decimal.Decimal
    """
    item = models.ForeignKey(
        Item,
        verbose_name=_("Item"),
        on_delete=models.PROTECT
    )
    variation = models.ForeignKey(
        ItemVariation,
        null=True, blank=True,
        verbose_name=_("Variation"),
        on_delete=models.PROTECT
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
    voucher = models.ForeignKey(
        'Voucher', null=True, blank=True
    )
    voucher_discount = models.DecimalField(
        default=Decimal('0.00'), decimal_places=2, max_digits=10
    )
    base_price = models.DecimalField(
        decimal_places=2, max_digits=10, null=True, blank=True
    )

    class Meta:
        abstract = True

    def cache_answers(self):
        """
        Creates two properties on the object.
        (1) answ: a dictionary of question.id → answer string
        (2) questions: a list of Question objects, extended by an 'answer' property
        """
        self.answ = {}
        for a in self.answers.all():
            self.answ[a.question_id] = a

        # We need to clone our question objects, otherwise we will override the cached
        # answers of other items in the same cart if the question objects have been
        # selected via prefetch_related
        self.questions = list(copy.copy(q) for q in self.item.questions.all())
        for q in self.questions:
            if q.id in self.answ:
                q.answer = self.answ[q.id]
            else:
                q.answer = ""

    def save(self, *args, **kwargs):
        if self.voucher is None and self.base_price is None:
            self.base_price = self.price
        if self.voucher_discount != Decimal('0.00') and self.base_price is not None:
            self.price = self.base_price - self.voucher_discount
        return super().save(*args, **kwargs)


class OrderPosition(AbstractPosition):
    """
    An OrderPosition is one line of an order, representing one ordered item
    of a specified type (or variation). This has all properties of
    AbstractPosition.

    :param order: The order this position is a part of
    :type order: Order
    """
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='positions',
        on_delete=models.PROTECT
    )
    tax_rate = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name=_('Tax rate')
    )
    tax_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name=_('Tax value')
    )
    secret = models.CharField(max_length=64, default=generate_position_secret, db_index=True)

    class Meta:
        verbose_name = _("Order position")
        verbose_name_plural = _("Order positions")

    @classmethod
    def transform_cart_positions(cls, cp: List, order) -> list:
        ops = []
        for cartpos in cp:
            op = OrderPosition(order=order)
            for f in AbstractPosition._meta.fields:
                setattr(op, f.name, getattr(cartpos, f.name))
            op._calculate_tax()
            op.save()
            for answ in cartpos.answers.all():
                answ.orderposition = op
                answ.cartposition = None
                answ.save()
            if cartpos.voucher:
                cartpos.voucher.redeemed = True
                cartpos.voucher.save()
            cartpos.delete()
        return ops

    def __repr__(self):
        return '<OrderPosition: item %d, variation %d for order %s>' % (
            self.item.id, self.variation.id if self.variation else 0, self.order_id
        )

    def _calculate_tax(self):
        self.tax_rate = self.item.tax_rate
        if self.tax_rate:
            self.tax_value = round_decimal(self.price * (1 - 100 / (100 + self.item.tax_rate)))
        else:
            self.tax_value = Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.tax_rate is None:
            self._calculate_tax()
        return super().save(*args, **kwargs)


class CartPosition(AbstractPosition):
    """
    A cart position is similar to an order line, except that it is not
    yet part of a binding order but just placed by some user in his or
    her cart. It therefore normally has a much shorter expiration time
    than an ordered position, but still blocks an item in the quota pool
    as we do not want to throw out users while they're clicking through
    the checkout process. This has all properties of AbstractPosition.

    :param event: The event this belongs to
    :type event: Evnt
    :param cart_id: The user session that contains this cart position
    :type cart_id: str
    """
    event = models.ForeignKey(
        Event,
        verbose_name=_("Event")
    )
    cart_id = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name=_("Cart ID (e.g. session key)")
    )
    datetime = models.DateTimeField(
        verbose_name=_("Date"),
        auto_now_add=True
    )
    expires = models.DateTimeField(
        verbose_name=_("Expiration date")
    )

    class Meta:
        verbose_name = _("Cart position")
        verbose_name_plural = _("Cart positions")

    def __repr__(self):
        return '<CartPosition: item %d, variation %d for cart %s>' % (
            self.item.id, self.variation.id if self.variation else 0, self.cart_id
        )

    @property
    def tax_rate(self):
        return self.item.tax_rate

    @property
    def tax_value(self):
        if not self.tax_rate:
            return Decimal('0.00')
        return round_decimal(self.price * (1 - 100 / (100 + self.item.tax_rate)))


class InvoiceAddress(models.Model):
    last_modified = models.DateTimeField(auto_now=True)
    order = models.OneToOneField(Order, null=True, blank=True, related_name='invoice_address')
    company = models.CharField(max_length=255, blank=True, verbose_name=_('Company name'))
    name = models.CharField(max_length=255, verbose_name=_('Name'), blank=True)
    street = models.TextField(verbose_name=_('Address'), blank=False)
    zipcode = models.CharField(max_length=30, verbose_name=_('ZIP code'), blank=False)
    city = models.CharField(max_length=255, verbose_name=_('City'), blank=False)
    country = models.CharField(max_length=255, verbose_name=_('Country'), blank=False)
    phone = models.CharField(max_length=255, blank=True, verbose_name=_('Phone number'))
    vat_id = models.CharField(max_length=255, blank=True, verbose_name=_('VAT ID'))
