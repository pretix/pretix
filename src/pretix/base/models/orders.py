import copy
import json
import os
import string
from datetime import datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Union

import dateutil
import pytz
from django.conf import settings
from django.db import models
from django.db.models import F, Sum
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.encoding import escape_uri_path
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import make_aware, now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_countries.fields import CountryField
from i18nfield.strings import LazyI18nString

from pretix.base.i18n import language
from pretix.base.models import User
from pretix.base.reldate import RelativeDateWrapper

from .base import LoggedModel
from .event import Event, SubEvent
from .items import Item, ItemVariation, Question, QuestionOption, Quota


def generate_secret():
    return get_random_string(length=16, allowed_chars=string.ascii_lowercase + string.digits)


def generate_position_secret():
    # Exclude o,0,1,i,l to avoid confusion with bad fonts/printers
    return get_random_string(length=settings.ENTROPY['ticket_secret'], allowed_chars='abcdefghjkmnpqrstuvwxyz23456789')


class Order(LoggedModel):
    """
    An order is created when a user clicks 'buy' on his cart. It holds
    several OrderPositions and is connected to a user. It has an
    expiration date: If items run out of capacity, orders which are over
    their expiration date might be canceled.

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
        * ``STATUS_CANCELED``
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
    :param payment_info: Arbitrary information stored by the payment provider
    :type payment_info: str
    :param total: The total amount of the order, including the payment fee
    :type total: decimal.Decimal
    :param comment: An internal comment that will only be visible to staff, and never displayed to the user
    :type comment: str
    :param download_reminder_sent: A field to indicate whether a download reminder has been sent.
    :type download_reminder_sent: boolean
    :param meta_info: Additional meta information on the order, JSON-encoded.
    :type meta_info: str
    """

    STATUS_PENDING = "n"
    STATUS_PAID = "p"
    STATUS_EXPIRED = "e"
    STATUS_CANCELED = "c"
    STATUS_REFUNDED = "r"
    STATUS_CHOICE = (
        (STATUS_PENDING, _("pending")),
        (STATUS_PAID, _("paid")),
        (STATUS_EXPIRED, _("expired")),
        (STATUS_CANCELED, _("canceled")),
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
    checkin_attention = models.BooleanField(
        verbose_name=_('Requires special attention'),
        default=False,
        help_text=_('If you set this, the check-in app will show a visible warning that tickets of this order require '
                    'special attention. This will not show any details or custom message, so you need to brief your '
                    'check-in staff how to handle these cases.')
    )
    expiry_reminder_sent = models.BooleanField(
        default=False
    )

    download_reminder_sent = models.BooleanField(
        default=False
    )
    meta_info = models.TextField(
        verbose_name=_("Meta information"),
        null=True, blank=True
    )

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ("-datetime",)

    def __str__(self):
        return self.full_code

    @cached_property
    def meta_info_data(self):
        return json.loads(self.meta_info)

    @property
    def full_code(self):
        """
        An order code which is unique among all events of a single organizer,
        built by concatenating the event slug and the order code.
        """
        return '{event}-{code}'.format(event=self.event.slug.upper(), code=self.code)

    @property
    def changable(self):
        return self.status in (Order.STATUS_PAID, Order.STATUS_PENDING)

    def save(self, *args, **kwargs):
        if not self.code:
            self.assign_code()
        if not self.datetime:
            self.datetime = now()
        super().save(*args, **kwargs)

    @cached_property
    def tax_total(self):
        return (self.positions.aggregate(s=Sum('tax_value'))['s'] or 0) + (self.fees.aggregate(s=Sum('tax_value'))['s'] or 0)

    @property
    def net_total(self):
        return self.total - self.tax_total

    def cancel_allowed(self):
        return (
            self.status == Order.STATUS_PENDING
            or (self.status == Order.STATUS_PAID and self.total == Decimal('0.00'))
        )

    @staticmethod
    def normalize_code(code):
        tr = str.maketrans({
            '2': 'Z',
            '4': 'A',
            '5': 'S',
            '6': 'G',
        })
        return code.upper().translate(tr)

    def assign_code(self):
        # This omits some character pairs completely because they are hard to read even on screens (1/I and O/0)
        # and includes only one of two characters for some pairs because they are sometimes hard to distinguish in
        # handwriting (2/Z, 4/A, 5/S, 6/G). This allows for better detection e.g. in incoming wire transfers that
        # might include OCR'd handwritten text
        charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
        while True:
            code = get_random_string(length=settings.ENTROPY['order_code'], allowed_chars=charset)
            if not Order.objects.filter(event__organizer=self.event.organizer, code=code).exists():
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

        modify_deadline = self.event.settings.get('last_order_modification_date', as_type=RelativeDateWrapper)
        if self.event.has_subevents and modify_deadline:
            modify_deadline = min([
                modify_deadline.datetime(se)
                for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
            ])
        elif modify_deadline:
            modify_deadline = modify_deadline.datetime(self.event)

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
    def can_user_cancel(self) -> bool:
        """
        Returns whether or not this order can be canceled by the user.
        """
        positions = self.positions.all().select_related('item')
        cancelable = all([op.item.allow_cancel for op in positions])
        return self.cancel_allowed() and self.event.settings.cancel_allow_user and cancelable

    @property
    def is_expired_by_time(self):
        return (
            self.status == Order.STATUS_PENDING and self.expires < now()
            and not self.event.settings.get('payment_term_expire_automatically')
        )

    @property
    def ticket_download_date(self):
        """
        Returns the first date the tickets for this order can be downloaded or ``None`` if there is no
        restriction.
        """
        dl_date = self.event.settings.get('ticket_download_date', as_type=RelativeDateWrapper)
        if dl_date:
            if self.event.has_subevents:
                dl_date = min([
                    dl_date.datetime(se)
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ])
            else:
                dl_date = dl_date.datetime(self.event)
        return dl_date

    @property
    def payment_term_last(self):
        tz = pytz.timezone(self.event.settings.timezone)
        term_last = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
        if term_last:
            if self.event.has_subevents:
                term_last = min([
                    term_last.datetime(se).date()
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ])
            else:
                term_last = term_last.datetime(self.event).date()
            term_last = make_aware(datetime.combine(
                term_last,
                time(hour=23, minute=59, second=59)
            ), tz)
        return term_last

    def _can_be_paid(self, count_waitinglist=True) -> Union[bool, str]:
        error_messages = {
            'late_lastdate': _("The payment can not be accepted as the last date of payments configured in the "
                               "payment settings is over."),
            'late': _("The payment can not be accepted as it the order is expired and you configured that no late "
                      "payments should be accepted in the payment settings."),
        }
        term_last = self.payment_term_last
        if term_last:
            if now() > term_last:
                return error_messages['late_lastdate']

        if self.status == self.STATUS_PENDING:
            return True
        if not self.event.settings.get('payment_term_accept_late'):
            return error_messages['late']

        return self._is_still_available(count_waitinglist=count_waitinglist)

    def _is_still_available(self, now_dt: datetime=None, count_waitinglist=True) -> Union[bool, str]:
        error_messages = {
            'unavailable': _('The ordered product "{item}" is no longer available.'),
        }
        now_dt = now_dt or now()
        positions = self.positions.all().select_related('item', 'variation')
        quota_cache = {}
        try:
            for i, op in enumerate(positions):
                quotas = list(op.quotas)
                if len(quotas) == 0:
                    raise Quota.QuotaExceededException(error_messages['unavailable'].format(
                        item=str(op.item) + (' - ' + str(op.variation) if op.variation else '')
                    ))

                for quota in quotas:
                    if quota.id not in quota_cache:
                        quota_cache[quota.id] = quota
                        quota.cached_availability = quota.availability(now_dt, count_waitinglist=count_waitinglist)[1]
                    else:
                        # Use cached version
                        quota = quota_cache[quota.id]
                    if quota.cached_availability is not None:
                        quota.cached_availability -= 1
                        if quota.cached_availability < 0:
                            # This quota is sold out/currently unavailable, so do not sell this at all
                            raise Quota.QuotaExceededException(error_messages['unavailable'].format(
                                item=str(op.item) + (' - ' + str(op.variation) if op.variation else '')
                            ))
        except Quota.QuotaExceededException as e:
            return str(e)
        return True

    def send_mail(self, subject: str, template: Union[str, LazyI18nString],
                  context: Dict[str, Any]=None, log_entry_type: str='pretix.event.order.email.sent',
                  user: User=None, headers: dict=None, sender: str=None, invoices: list=None):
        """
        Sends an email to the user that placed this order. Basically, this method does two things:

        * Call ``pretix.base.services.mail.mail`` with useful values for the ``event``, ``locale``, ``recipient`` and
          ``order`` parameters.

        * Create a ``LogEntry`` with the email contents.

        :param subject: Subject of the email
        :param template: LazyI18nString or template filename, see ``pretix.base.services.mail.mail`` for more details
        :param context: Dictionary to use for rendering the template
        :param log_entry_type: Key to be used for the log entry
        :param user: Administrative user who triggered this mail to be sent
        :param headers: Dictionary with additional mail headers
        :param sender: Custom email sender.
        """
        from pretix.base.services.mail import SendMailException, mail, render_mail

        if not self.email:
            return

        with language(self.locale):
            recipient = self.email
            try:
                email_content = render_mail(template, context)[0]
                mail(
                    recipient, subject, template, context,
                    self.event, self.locale, self, headers, sender,
                    invoices=invoices
                )
            except SendMailException:
                raise
            else:
                self.log_action(
                    log_entry_type,
                    user=user,
                    data={
                        'subject': subject,
                        'message': email_content,
                        'recipient': recipient,
                        'invoices': [i.pk for i in invoices] if invoices else []
                    }
                )


def answerfile_name(instance, filename: str) -> str:
    secret = get_random_string(length=32, allowed_chars=string.ascii_letters + string.digits)
    event = (instance.cartposition if instance.cartposition else instance.orderposition.order).event
    return 'cachedfiles/answers/{org}/{ev}/{secret}.{filename}'.format(
        org=event.organizer.slug,
        ev=event.slug,
        secret=secret,
        filename=escape_uri_path(filename),
    )


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
    file = models.FileField(
        null=True, blank=True, upload_to=answerfile_name
    )

    @property
    def backend_file_url(self):
        if self.file:
            if self.orderposition:
                return reverse('control:event.order.download.answer', kwargs={
                    'code': self.orderposition.order.code,
                    'event': self.orderposition.order.event.slug,
                    'organizer': self.orderposition.order.event.organizer.slug,
                    'answer': self.pk,
                })
        return ""

    @property
    def frontend_file_url(self):
        from pretix.multidomain.urlreverse import eventreverse

        if self.file:
            if self.orderposition:
                url = eventreverse(self.orderposition.order.event, 'presale:event.order.download.answer', kwargs={
                    'order': self.orderposition.order.code,
                    'secret': self.orderposition.order.secret,
                    'answer': self.pk,
                })
            else:
                url = eventreverse(self.cartposition.event, 'presale:event.cart.download.answer', kwargs={
                    'answer': self.pk,
                })

            return url
        return ""

    @property
    def file_name(self):
        return self.file.name.split('.', 1)[-1]

    def __str__(self):
        if self.question.type == Question.TYPE_BOOLEAN and self.answer == "True":
            return str(_("Yes"))
        elif self.question.type == Question.TYPE_BOOLEAN and self.answer == "False":
            return str(_("No"))
        elif self.question.type == Question.TYPE_FILE:
            return str(_("<file>"))
        elif self.question.type == Question.TYPE_DATETIME and self.answer:
            try:
                d = dateutil.parser.parse(self.answer)
                if self.orderposition:
                    tz = pytz.timezone(self.orderposition.order.event.settings.timezone)
                    d = d.astimezone(tz)
                return date_format(d, "SHORT_DATETIME_FORMAT")
            except ValueError:
                return self.answer
        elif self.question.type == Question.TYPE_DATE and self.answer:
            try:
                d = dateutil.parser.parse(self.answer)
                return date_format(d, "SHORT_DATE_FORMAT")
            except ValueError:
                return self.answer
        elif self.question.type == Question.TYPE_TIME and self.answer:
            try:
                d = dateutil.parser.parse(self.answer)
                return date_format(d, "TIME_FORMAT")
            except ValueError:
                return self.answer
        else:
            return self.answer

    def save(self, *args, **kwargs):
        if self.orderposition and self.cartposition:
            raise ValueError('QuestionAnswer cannot be linked to an order and a cart position at the same time.')
        super().save(*args, **kwargs)


class AbstractPosition(models.Model):
    """
    A position can either be one line of an order or an item placed in a cart.

    :param subevent: The date in the event series, if event series are enabled
    :type subevent: SubEvent
    :param item: The selected item
    :type item: Item
    :param variation: The selected ItemVariation or null, if the item has no variations
    :type variation: ItemVariation
    :param datetime: The datetime this item was put into the cart
    :type datetime: datetime
    :param expires: The date until this item is guaranteed to be reserved
    :type expires: datetime
    :param price: The price of this item
    :type price: decimal.Decimal
    :param attendee_name: The attendee's name, if entered.
    :type attendee_name: str
    :param attendee_email: The attendee's email, if entered.
    :type attendee_email: str
    :param voucher: A voucher that has been applied to this sale
    :type voucher: Voucher
    :param meta_info: Additional meta information on the position, JSON-encoded.
    :type meta_info: str
    """
    subevent = models.ForeignKey(
        SubEvent,
        null=True, blank=True,
        on_delete=models.CASCADE,
        verbose_name=pgettext_lazy("subevent", "Date"),
    )
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
    attendee_email = models.EmailField(
        verbose_name=_("Attendee email"),
        blank=True, null=True,
        help_text=_("Empty, if this product is not an admission ticket")
    )
    voucher = models.ForeignKey(
        'Voucher', null=True, blank=True
    )
    addon_to = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE, related_name='addons'
    )
    meta_info = models.TextField(
        verbose_name=_("Meta information"),
        null=True, blank=True
    )

    class Meta:
        abstract = True

    @property
    def meta_info_data(self):
        if self.meta_info:
            return json.loads(self.meta_info)
        else:
            return {}

    def cache_answers(self, all=True):
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
        if not all:
            if hasattr(self.item, 'questions_to_ask'):
                self.questions = list(copy.copy(q) for q in self.item.questions_to_ask)
            else:
                self.questions = list(copy.copy(q) for q in self.item.questions.filter(ask_during_checkin=False))
        else:
            self.questions = list(copy.copy(q) for q in self.item.questions.all())
        for q in self.questions:
            if q.id in self.answ:
                q.answer = self.answ[q.id]
            else:
                q.answer = ""

    @property
    def net_price(self):
        return self.price - self.tax_value

    @property
    def quotas(self):
        return (self.item.quotas.filter(subevent=self.subevent)
                if self.variation is None
                else self.variation.quotas.filter(subevent=self.subevent))


class OrderFee(models.Model):
    """
    An OrderFee objet represents a fee that is added to the order total independently of
    the actual positions. This might for example be a payment or a shipping fee.
    """
    FEE_TYPE_PAYMENT = "payment"
    FEE_TYPE_SHIPPING = "shipping"
    FEE_TYPE_SERVICE = "service"
    FEE_TYPE_OTHER = "other"
    FEE_TYPES = (
        (FEE_TYPE_PAYMENT, _("Payment fee")),
        (FEE_TYPE_SHIPPING, _("Shipping fee")),
        (FEE_TYPE_SERVICE, _("Service fee")),
        (FEE_TYPE_OTHER, _("Other fees")),
    )

    value = models.DecimalField(
        decimal_places=2, max_digits=10,
        verbose_name=_("Value")
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='fees',
        on_delete=models.PROTECT
    )
    fee_type = models.CharField(
        max_length=100, choices=FEE_TYPES
    )
    description = models.CharField(max_length=190, blank=True)
    internal_type = models.CharField(max_length=255, blank=True)
    tax_rate = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name=_('Tax rate')
    )
    tax_rule = models.ForeignKey(
        'TaxRule',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    tax_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name=_('Tax value')
    )

    @property
    def net_value(self):
        return self.value - self.tax_value

    def __str__(self):
        if self.description:
            return '{} - {}'.format(self.get_fee_type_display(), self.description)
        else:
            return self.get_fee_type_display()

    def __repr__(self):
        return '<OrderFee: type %s, value %d>' % (
            self.fee_type, self.value
        )

    def _calculate_tax(self):
        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None

        if not self.tax_rule and self.fee_type == "payment" and self.order.event.settings.tax_rate_default:
            self.tax_rule = self.order.event.settings.tax_rate_default

        if self.tax_rule:
            if self.tax_rule.tax_applicable(ia):
                tax = self.tax_rule.tax(self.value, base_price_is='gross')
                self.tax_rate = tax.rate
                self.tax_value = tax.tax
            else:
                self.tax_value = Decimal('0.00')
                self.tax_rate = Decimal('0.00')
        else:
            self.tax_value = Decimal('0.00')
            self.tax_rate = Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.tax_rate is None:
            self._calculate_tax()
        return super().save(*args, **kwargs)


class OrderPosition(AbstractPosition):
    """
    An OrderPosition is one line of an order, representing one ordered item
    of a specified type (or variation). This has all properties of
    AbstractPosition.

    :param order: The order this position is a part of
    :type order: Order
    """
    positionid = models.PositiveIntegerField(default=1)
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
    tax_rule = models.ForeignKey(
        'TaxRule',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    tax_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name=_('Tax value')
    )
    secret = models.CharField(max_length=64, default=generate_position_secret, db_index=True)

    class Meta:
        verbose_name = _("Order position")
        verbose_name_plural = _("Order positions")
        ordering = ("positionid", "id")

    @cached_property
    def sort_key(self):
        return self.addon_to.positionid if self.addon_to else self.positionid, self.addon_to_id or 0

    @classmethod
    def transform_cart_positions(cls, cp: List, order) -> list:
        from . import Voucher

        ops = []
        cp_mapping = {}
        # The sorting key ensures that all addons come directly after the position they refer to
        for i, cartpos in enumerate(sorted(cp, key=lambda c: (c.addon_to_id or c.pk, c.addon_to_id or 0))):
            op = OrderPosition(order=order)
            for f in AbstractPosition._meta.fields:
                if f.name == 'addon_to':
                    setattr(op, f.name, cp_mapping.get(cartpos.addon_to_id))
                else:
                    setattr(op, f.name, getattr(cartpos, f.name))
            op._calculate_tax()
            op.positionid = i + 1
            op.save()
            cp_mapping[cartpos.pk] = op
            for answ in cartpos.answers.all():
                answ.orderposition = op
                answ.cartposition = None
                answ.save()
            if cartpos.voucher:
                Voucher.objects.filter(pk=cartpos.voucher.pk).update(redeemed=F('redeemed') + 1)
                cartpos.voucher.log_action('pretix.voucher.redeemed', {
                    'order_code': order.code
                })

        # Delete afterwards. Deleting in between might cause deletion of things related to add-ons
        # due to the deletion cascade.
        for cartpos in cp:
            cartpos.delete()
        return ops

    def __str__(self):
        if self.variation:
            return '#{} – {} – {}'.format(
                self.positionid, str(self.item), str(self.variation)
            )
        return '#{} – {}'.format(self.positionid, str(self.item))

    def __repr__(self):
        return '<OrderPosition: item %d, variation %d for order %s>' % (
            self.item.id, self.variation.id if self.variation else 0, self.order_id
        )

    def _calculate_tax(self):
        self.tax_rule = self.item.tax_rule
        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None
        if self.tax_rule:
            if self.tax_rule.tax_applicable(ia):
                tax = self.tax_rule.tax(self.price, base_price_is='gross')
                self.tax_rate = tax.rate
                self.tax_value = tax.tax
            else:
                self.tax_value = Decimal('0.00')
                self.tax_rate = Decimal('0.00')
        else:
            self.tax_value = Decimal('0.00')
            self.tax_rate = Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.tax_rate is None:
            self._calculate_tax()
        if self.pk is None:
            while OrderPosition.objects.filter(secret=self.secret).exists():
                self.secret = generate_position_secret()
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
    :type event: Event
    :param cart_id: The user session that contains this cart position
    :type cart_id: str
    """
    event = models.ForeignKey(
        Event,
        verbose_name=_("Event")
    )
    cart_id = models.CharField(
        max_length=255, null=True, blank=True, db_index=True,
        verbose_name=_("Cart ID (e.g. session key)")
    )
    datetime = models.DateTimeField(
        verbose_name=_("Date"),
        auto_now_add=True
    )
    expires = models.DateTimeField(
        verbose_name=_("Expiration date"),
        db_index=True
    )
    includes_tax = models.BooleanField(
        default=True
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
        if self.includes_tax:
            return self.item.tax(self.price, base_price_is='gross').rate
        else:
            return Decimal('0.00')

    @property
    def tax_value(self):
        if self.includes_tax:
            return self.item.tax(self.price, base_price_is='gross').tax
        else:
            return Decimal('0.00')


class InvoiceAddress(models.Model):
    last_modified = models.DateTimeField(auto_now=True)
    order = models.OneToOneField(Order, null=True, blank=True, related_name='invoice_address')
    is_business = models.BooleanField(default=False, verbose_name=_('Business customer'))
    company = models.CharField(max_length=255, blank=True, verbose_name=_('Company name'))
    name = models.CharField(max_length=255, verbose_name=_('Full name'), blank=True)
    street = models.TextField(verbose_name=_('Address'), blank=False)
    zipcode = models.CharField(max_length=30, verbose_name=_('ZIP code'), blank=False)
    city = models.CharField(max_length=255, verbose_name=_('City'), blank=False)
    country_old = models.CharField(max_length=255, verbose_name=_('Country'), blank=False)
    country = CountryField(verbose_name=_('Country'), blank=False, blank_label=_('Select country'))
    vat_id = models.CharField(max_length=255, blank=True, verbose_name=_('VAT ID'),
                              help_text=_('Only for business customers within the EU.'))
    vat_id_validated = models.BooleanField(default=False)
    internal_reference = models.TextField(
        verbose_name=_('Internal reference'),
        help_text=_('This reference will be printed on your invoice for your convenience.'),
        blank=True
    )


def cachedticket_name(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'tickets/{org}/{ev}/{code}-{no}-{prov}-{secret}.dat'.format(
        org=instance.order_position.order.event.organizer.slug,
        ev=instance.order_position.order.event.slug,
        prov=instance.provider,
        no=instance.order_position.positionid,
        code=instance.order_position.order.code,
        secret=secret,
        ext=os.path.splitext(filename)[1]
    )


def cachedcombinedticket_name(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'tickets/{org}/{ev}/{code}-{prov}-{secret}.dat'.format(
        org=instance.order.event.organizer.slug,
        ev=instance.order.event.slug,
        prov=instance.provider,
        code=instance.order.code,
        secret=secret
    )


class CachedTicket(models.Model):
    order_position = models.ForeignKey(OrderPosition, on_delete=models.CASCADE)
    provider = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    extension = models.CharField(max_length=255)
    file = models.FileField(null=True, blank=True, upload_to=cachedticket_name)
    created = models.DateTimeField(auto_now_add=True)


class CachedCombinedTicket(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    provider = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    extension = models.CharField(max_length=255)
    file = models.FileField(null=True, blank=True, upload_to=cachedcombinedticket_name)
    created = models.DateTimeField(auto_now_add=True)


@receiver(post_delete, sender=CachedTicket)
def cachedticket_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)


@receiver(post_delete, sender=CachedCombinedTicket)
def cachedcombinedticket_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)


@receiver(post_delete, sender=QuestionAnswer)
def answer_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)
