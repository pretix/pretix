import string
import uuid
from datetime import date, datetime, time

import pytz
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.mail import get_connection
from django.core.validators import RegexValidator
from django.db import models
from django.template.defaultfilters import date as _date
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import make_aware, now
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nCharField

from pretix.base.email import CustomSMTPBackend
from pretix.base.models.base import LoggedModel
from pretix.base.settings import SettingsProxy
from pretix.base.validators import EventSlugBlacklistValidator
from pretix.helpers.daterange import daterange

from .auth import User
from .organizer import Organizer
from .settings import EventSetting


class Event(LoggedModel):
    """
    This model represents an event. An event is anything you can buy
    tickets for.

    :param organizer: The organizer this event belongs to
    :type organizer: Organizer
    :param name: This event's full title
    :type name: str
    :param slug: A short, alphanumeric, all-lowercase name for use in URLs. The slug has to
                 be unique among the events of the same organizer.
    :type slug: str
    :param live: Whether or not the shop is publicly accessible
    :type live: bool
    :param currency: The currency of all prices and payments of this event
    :type currency: str
    :param date_from: The datetime this event starts
    :type date_from: datetime
    :param date_to: The datetime this event ends
    :type date_to: datetime
    :param presale_start: No tickets will be sold before this date.
    :type presale_start: datetime
    :param presale_end: No tickets will be sold after this date.
    :type presale_end: datetime
    :param location: venue
    :type location: str
    :param plugins: A comma-separated list of plugin names that are active for this
                    event.
    :type plugins: str
    """

    settings_namespace = 'event'
    organizer = models.ForeignKey(Organizer, related_name="events", on_delete=models.PROTECT)
    name = I18nCharField(
        max_length=200,
        verbose_name=_("Name"),
    )
    slug = models.SlugField(
        max_length=50, db_index=True,
        help_text=_(
            "Should be short, only contain lowercase letters and numbers, and must be unique among your events. "
            "This will be used in order codes, invoice numbers, links and bank transfer references."),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9.-]+$",
                message=_("The slug may only contain letters, numbers, dots and dashes."),
            ),
            EventSlugBlacklistValidator()
        ],
        verbose_name=_("Short form"),
    )
    live = models.BooleanField(default=False, verbose_name=_("Shop is live"))
    permitted = models.ManyToManyField(User, through='EventPermission',
                                       related_name="events", )
    currency = models.CharField(max_length=10,
                                verbose_name=_("Default currency"),
                                default=settings.DEFAULT_CURRENCY)
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
    is_public = models.BooleanField(default=False,
                                    verbose_name=_("Visible in public lists"),
                                    help_text=_("If selected, this event may show up on the ticket system's start page "
                                                "or an organization profile."))
    presale_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("End of presale"),
        help_text=_("No products will be sold after this date."),
    )
    presale_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Start of presale"),
        help_text=_("No products will be sold before this date."),
    )
    location = I18nCharField(
        null=True, blank=True,
        max_length=200,
        verbose_name=_("Location"),
    )
    plugins = models.TextField(
        null=True, blank=True,
        verbose_name=_("Plugins"),
    )

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        ordering = ("date_from", "name")

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)
        self.get_cache().clear()
        return obj

    def clean(self):
        if self.presale_start and self.presale_end and self.presale_start > self.presale_end:
            raise ValidationError({'presale_end': _('The end of the presale period has to be later than its start.')})
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError({'date_to': _('The end of the event has to be later than its start.')})
        super().clean()

    def get_plugins(self) -> "list[str]":
        """
        Returns the names of the plugins activated for this event as a list.
        """
        if self.plugins is None:
            return []
        return self.plugins.split(",")

    def get_date_from_display(self, tz=None) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting.
        """
        tz = tz or pytz.timezone(self.settings.timezone)
        return _date(
            self.date_from.astimezone(tz),
            "DATETIME_FORMAT" if self.settings.show_times else "DATE_FORMAT"
        )

    def get_date_to_display(self, tz=None) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting. Returns an empty string
        if ``show_date_to`` is ``False``.
        """
        tz = tz or pytz.timezone(self.settings.timezone)
        if not self.settings.show_date_to or not self.date_to:
            return ""
        return _date(
            self.date_to.astimezone(tz),
            "DATETIME_FORMAT" if self.settings.show_times else "DATE_FORMAT"
        )

    def get_date_range_display(self, tz=None) -> str:
        tz = tz or pytz.timezone(self.settings.timezone)
        if not self.settings.show_date_to or not self.date_to:
            return _date(self.date_from.astimezone(tz), "DATE_FORMAT")
        return daterange(self.date_from.astimezone(tz), self.date_to.astimezone(tz))

    def get_cache(self) -> "pretix.base.cache.ObjectRelatedCache":
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this event, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the event or one of its related objects change.
        """
        from pretix.base.cache import ObjectRelatedCache

        return ObjectRelatedCache(self)

    @cached_property
    def settings(self) -> SettingsProxy:
        """
        Returns an object representing this event's settings.
        """
        try:
            return SettingsProxy(self, type=EventSetting, parent=self.organizer)
        except Organizer.DoesNotExist:
            # Should only happen when creating new events
            return SettingsProxy(self, type=EventSetting)

    @property
    def presale_has_ended(self):
        if self.presale_end and now() > self.presale_end:
            return True
        return False

    @property
    def presale_is_running(self):
        if self.presale_start and now() < self.presale_start:
            return False
        if self.presale_end and now() > self.presale_end:
            return False
        return True

    def lock(self):
        """
        Returns a contextmanager that can be used to lock an event for bookings.
        """
        from pretix.base.services import locking

        return locking.LockManager(self)

    def get_mail_backend(self, force_custom=False):
        if self.settings.smtp_use_custom or force_custom:
            return CustomSMTPBackend(host=self.settings.smtp_host,
                                     port=self.settings.smtp_port,
                                     username=self.settings.smtp_username,
                                     password=self.settings.smtp_password,
                                     use_tls=self.settings.smtp_use_tls,
                                     use_ssl=self.settings.smtp_use_ssl,
                                     fail_silently=False)
        else:
            return get_connection(fail_silently=False)

    @property
    def payment_term_last(self):
        tz = pytz.timezone(self.settings.timezone)
        return make_aware(datetime.combine(
            self.settings.get('payment_term_last', as_type=date),
            time(hour=23, minute=59, second=59)
        ), tz)

    def copy_data_from(self, other):
        from . import ItemCategory, Item, Question, Quota
        self.plugins = other.plugins
        self.save()

        category_map = {}
        for c in ItemCategory.objects.filter(event=other):
            category_map[c.pk] = c
            c.pk = None
            c.event = self
            c.save()

        item_map = {}
        variation_map = {}
        for i in Item.objects.filter(event=other).prefetch_related('variations'):
            vars = list(i.variations.all())
            item_map[i.pk] = i
            i.pk = None
            i.event = self
            if i.picture:
                i.picture.save(i.picture.name, i.picture)
            if i.category_id:
                i.category = category_map[i.category_id]
            i.save()
            for v in vars:
                variation_map[v.pk] = v
                v.pk = None
                v.item = i
                v.save()

        for q in Quota.objects.filter(event=other).prefetch_related('items', 'variations'):
            items = list(q.items.all())
            vars = list(q.variations.all())
            q.pk = None
            q.event = self
            q.save()
            for i in items:
                q.items.add(item_map[i.pk])
            for v in vars:
                q.variations.add(variation_map[v.pk])

        for q in Question.objects.filter(event=other).prefetch_related('items', 'options'):
            items = list(q.items.all())
            opts = list(q.options.all())
            q.pk = None
            q.event = self
            q.save()
            for i in items:
                q.items.add(item_map[i.pk])
            for o in opts:
                o.pk = None
                o.question = q
                o.save()

        for s in EventSetting.objects.filter(object=other):
            s.object = self
            s.pk = None
            if s.value.startswith('file://'):
                fi = default_storage.open(s.value[7:], 'rb')
                nonce = get_random_string(length=8)
                fname = '%s/%s/%s.%s.%s' % (
                    self.organizer.slug, self.slug, s.key, nonce, s.value.split('.')[-1]
                )
                newname = default_storage.save(fname, fi)
                s.value = 'file://' + newname
            s.save()


def generate_invite_token():
    return get_random_string(length=32, allowed_chars=string.ascii_lowercase + string.digits)


class EventPermission(models.Model):
    """
    The relation between an Event and a User who has permissions to
    access an event.

    :param event: The event this permission refers to
    :type event: Event
    :param user: The user this permission set applies to
    :type user: User
    :param can_change_settings: If ``True``, the user can change all basic settings for this event.
    :type can_change_settings: bool
    :param can_change_items: If ``True``, the user can change and add items and related objects for this event.
    :type can_change_items: bool
    :param can_view_orders: If ``True``, the user can inspect details of all orders.
    :type can_view_orders: bool
    :param can_change_orders: If ``True``, the user can change details of orders
    :type can_change_orders: bool
    """

    event = models.ForeignKey(Event, related_name="user_perms", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="event_perms", on_delete=models.CASCADE, null=True, blank=True)
    invite_email = models.EmailField(null=True, blank=True)
    invite_token = models.CharField(default=generate_invite_token, max_length=64, null=True, blank=True)
    can_change_settings = models.BooleanField(
        default=True,
        verbose_name=_("Can change event settings")
    )
    can_change_items = models.BooleanField(
        default=True,
        verbose_name=_("Can change product settings")
    )
    can_view_orders = models.BooleanField(
        default=True,
        verbose_name=_("Can view orders")
    )
    can_change_permissions = models.BooleanField(
        default=True,
        verbose_name=_("Can change permissions")
    )
    can_change_orders = models.BooleanField(
        default=True,
        verbose_name=_("Can change orders")
    )
    can_view_vouchers = models.BooleanField(
        default=True,
        verbose_name=_("Can view vouchers")
    )
    can_change_vouchers = models.BooleanField(
        default=True,
        verbose_name=_("Can change vouchers")
    )

    class Meta:
        verbose_name = _("Event permission")
        verbose_name_plural = _("Event permissions")

    def __str__(self):
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.event),
        }


class EventLock(models.Model):
    event = models.CharField(max_length=36, primary_key=True)
    date = models.DateTimeField(auto_now=True)
    token = models.UUIDField(default=uuid.uuid4)


class RequiredAction(models.Model):
    """
    Represents an action that is to be done by an admin. The admin will be
    displayed a list of actions to do.

    :param datatime: The timestamp of the required action
    :type datetime: datetime
    :param user: The user that performed the action
    :type user: User
    :param done: If this action has been completed or dismissed
    :type done: bool
    :param action_type: The type of action that has to be performed. This is
       used to look up the renderer used to describe the action in a human-
       readable way. This should be some namespaced value using dotted
       notation to avoid duplicates, e.g.
       ``"pretix.plugins.banktransfer.incoming_transfer"``.
    :type action_type: str
    :param data: Arbitrary data that can be used by the log action renderer
    :type data: str
    """
    datetime = models.DateTimeField(auto_now_add=True, db_index=True)
    done = models.BooleanField(default=False)
    user = models.ForeignKey('User', null=True, blank=True, on_delete=models.PROTECT)
    event = models.ForeignKey('Event', null=True, blank=True, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=255)
    data = models.TextField(default='{}')

    class Meta:
        ordering = ('datetime',)

    def display(self, request):
        from ..signals import requiredaction_display

        for receiver, response in requiredaction_display.send(self.event, action=self, request=request):
            if response:
                return response
        return self.action_type
