import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import get_connection
from django.core.validators import RegexValidator
from django.db import models
from django.template.defaultfilters import date as _date
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.email import CustomSMTPBackend
from pretix.base.i18n import I18nCharField
from pretix.base.models.base import LoggedModel
from pretix.base.settings import SettingsProxy

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
    :param plugins: A comma-separated list of plugin names that are active for this
                    event.
    :type plugins: str
    """

    organizer = models.ForeignKey(Organizer, related_name="events", on_delete=models.PROTECT)
    name = I18nCharField(
        max_length=200,
        verbose_name=_("Name"),
    )
    slug = models.SlugField(
        max_length=50, db_index=True,
        help_text=_(
            "Should be short, only contain lowercase letters and numbers, and must be unique among your events. "
            "This is being used in addresses and bank transfer references."),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9.-]+$",
                message=_("The slug may only contain letters, numbers, dots and dashes."),
            )
        ],
        verbose_name=_("Slug"),
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

    def get_date_from_display(self) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting.
        """
        return _date(
            self.date_from,
            "DATETIME_FORMAT" if self.settings.show_times else "DATE_FORMAT"
        )

    def get_date_to_display(self) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting. Returns an empty string
        if ``show_date_to`` is ``False``.
        """
        if not self.settings.show_date_to:
            return ""
        return _date(
            self.date_to,
            "DATETIME_FORMAT" if self.settings.show_times else "DATE_FORMAT"
        )

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
    user = models.ForeignKey(User, related_name="event_perms", on_delete=models.CASCADE)
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
