import string
import uuid
from collections import OrderedDict
from datetime import datetime, time

import pytz
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.mail import get_connection
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Exists, OuterRef, Q
from django.template.defaultfilters import date as _date
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import make_aware, now
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nCharField, I18nTextField

from pretix.base.email import CustomSMTPBackend
from pretix.base.models.base import LoggedModel
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.validators import EventSlugBlacklistValidator
from pretix.helpers.daterange import daterange
from pretix.helpers.json import safe_string

from ..settings import settings_hierarkey
from .organizer import Organizer, Team


class EventMixin:

    def clean(self):
        if self.presale_start and self.presale_end and self.presale_start > self.presale_end:
            raise ValidationError({'presale_end': _('The end of the presale period has to be later than its start.')})
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError({'date_to': _('The end of the event has to be later than its start.')})
        super().clean()

    def get_short_date_from_display(self, tz=None, show_times=True) -> str:
        """
        Returns a shorter formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting.
        """
        tz = tz or self.timezone
        return _date(
            self.date_from.astimezone(tz),
            "SHORT_DATETIME_FORMAT" if self.settings.show_times and show_times else "DATE_FORMAT"
        )

    def get_short_date_to_display(self, tz=None) -> str:
        """
        Returns a shorter formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting. Returns an empty string
        if ``show_date_to`` is ``False``.
        """
        tz = tz or self.timezone
        if not self.settings.show_date_to or not self.date_to:
            return ""
        return _date(
            self.date_to.astimezone(tz),
            "SHORT_DATETIME_FORMAT" if self.settings.show_times else "DATE_FORMAT"
        )

    def get_date_from_display(self, tz=None, show_times=True) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting.
        """
        tz = tz or self.timezone
        return _date(
            self.date_from.astimezone(tz),
            "DATETIME_FORMAT" if self.settings.show_times and show_times else "DATE_FORMAT"
        )

    def get_time_from_display(self, tz=None) -> str:
        """
        Returns a formatted string containing the start time of the event, ignoring
        the ``show_times`` setting.
        """
        tz = tz or self.timezone
        return _date(
            self.date_from.astimezone(tz), "TIME_FORMAT"
        )

    def get_date_to_display(self, tz=None) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting. Returns an empty string
        if ``show_date_to`` is ``False``.
        """
        tz = tz or self.timezone
        if not self.settings.show_date_to or not self.date_to:
            return ""
        return _date(
            self.date_to.astimezone(tz),
            "DATETIME_FORMAT" if self.settings.show_times else "DATE_FORMAT"
        )

    def get_date_range_display(self, tz=None) -> str:
        """
        Returns a formatted string containing the start date and the end date
        of the event with respect to the current locale and to the ``show_times`` and
        ``show_date_to`` settings.
        """
        tz = tz or self.timezone
        if not self.settings.show_date_to or not self.date_to:
            return _date(self.date_from.astimezone(tz), "DATE_FORMAT")
        return daterange(self.date_from.astimezone(tz), self.date_to.astimezone(tz))

    @property
    def timezone(self):
        return pytz.timezone(self.settings.timezone)

    @property
    def presale_has_ended(self):
        """
        Is true, when ``presale_end`` is set and in the past.
        """
        if self.presale_end:
            return now() > self.presale_end
        elif self.date_to:
            return now() > self.date_to
        else:
            return now().astimezone(self.timezone).date() > self.date_from.astimezone(self.timezone).date()

    @property
    def presale_is_running(self):
        """
        Is true, when ``presale_end`` is not set or in the future and ``presale_start`` is not
        set or in the past.
        """
        if self.presale_start and now() < self.presale_start:
            return False
        return not self.presale_has_ended

    @property
    def event_microdata(self):
        import json

        eventdict = {
            "@context": "http://schema.org",
            "@type": "Event", "location": {
                "@type": "Place",
                "address": str(self.location)
            },
            "name": str(self.name)
        }

        if self.settings.show_times:
            eventdict["startDate"] = self.date_from.isoformat()
            if self.settings.show_date_to and self.date_to is not None:
                eventdict["endDate"] = self.date_to.isoformat()
        else:
            eventdict["startDate"] = self.date_from.date().isoformat()
            if self.settings.show_date_to and self.date_to is not None:
                eventdict["endDate"] = self.date_to.date().isoformat()

        return safe_string(json.dumps(eventdict))


@settings_hierarkey.add(parent_field='organizer', cache_namespace='event')
class Event(EventMixin, LoggedModel):
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
    :param has_subevents: Enable event series functionality
    :type has_subevents: bool
    """

    settings_namespace = 'event'
    CURRENCY_CHOICES = [(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES]
    organizer = models.ForeignKey(Organizer, related_name="events", on_delete=models.PROTECT)
    name = I18nCharField(
        max_length=200,
        verbose_name=_("Event name"),
    )
    slug = models.SlugField(
        max_length=50, db_index=True,
        help_text=_(
            "Should be short, only contain lowercase letters, numbers, dots, and dashes, and must be unique among your "
            "events. We recommend some kind of abbreviation or a date with less than 10 characters that can be easily "
            "remembered, but you can also choose to use a random value. "
            "This will be used in URLs, order codes, invoice numbers, and bank transfer references."),
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
    currency = models.CharField(max_length=10,
                                verbose_name=_("Event currency"),
                                choices=CURRENCY_CHOICES,
                                default=settings.DEFAULT_CURRENCY)
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
    date_admission = models.DateTimeField(null=True, blank=True,
                                          verbose_name=_("Admission time"))
    is_public = models.BooleanField(default=False,
                                    verbose_name=_("Visible in public lists"),
                                    help_text=_("If selected, this event may show up on the ticket system's start page "
                                                "or an organization profile."))
    presale_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("End of presale"),
        help_text=_("Optional. No products will be sold after this date. If you do not set this value, the presale "
                    "will end after the end date of your event."),
    )
    presale_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Start of presale"),
        help_text=_("Optional. No products will be sold before this date."),
    )
    location = I18nTextField(
        null=True, blank=True,
        max_length=200,
        verbose_name=_("Location"),
    )
    plugins = models.TextField(
        null=True, blank=True,
        verbose_name=_("Plugins"),
    )
    comment = models.TextField(
        verbose_name=_("Internal comment"),
        null=True, blank=True
    )
    has_subevents = models.BooleanField(
        verbose_name=_('Event series'),
        default=False
    )

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        ordering = ("date_from", "name")

    def __str__(self):
        return str(self.name)

    @property
    def presale_has_ended(self):
        if self.has_subevents:
            return self.presale_end and now() > self.presale_end
        else:
            return super().presale_has_ended

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)
        self.cache.clear()
        return obj

    def get_plugins(self) -> "list[str]":
        """
        Returns the names of the plugins activated for this event as a list.
        """
        if self.plugins is None:
            return []
        return self.plugins.split(",")

    def get_cache(self) -> "pretix.base.cache.ObjectRelatedCache":
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this event, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the event or one of its related objects change.

        .. deprecated:: 1.9
           Use the property ``cache`` instead.
        """
        return self.cache

    @cached_property
    def cache(self):
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this event, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the event or one of its related objects change.
        """
        from pretix.base.cache import ObjectRelatedCache

        return ObjectRelatedCache(self)

    def lock(self):
        """
        Returns a contextmanager that can be used to lock an event for bookings.
        """
        from pretix.base.services import locking

        return locking.LockManager(self)

    def get_mail_backend(self, force_custom=False):
        """
        Returns an email server connection, either by using the system-wide connection
        or by returning a custom one based on the event's settings.
        """
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
        """
        The last datetime of payments for this event.
        """
        tz = pytz.timezone(self.settings.timezone)
        return make_aware(datetime.combine(
            self.settings.get('payment_term_last', as_type=RelativeDateWrapper).datetime(self).date(),
            time(hour=23, minute=59, second=59)
        ), tz)

    def copy_data_from(self, other):
        from . import ItemAddOn, ItemCategory, Item, Question, Quota
        from ..signals import event_copy_data

        self.plugins = other.plugins
        self.is_public = other.is_public
        self.save()

        tax_map = {}
        for t in other.tax_rules.all():
            tax_map[t.pk] = t
            t.pk = None
            t.event = self
            t.save()

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
            if i.tax_rule_id:
                i.tax_rule = tax_map[i.tax_rule_id]
            i.save()
            for v in vars:
                variation_map[v.pk] = v
                v.pk = None
                v.item = i
                v.save()

        for ia in ItemAddOn.objects.filter(base_item__event=other).prefetch_related('base_item', 'addon_category'):
            ia.pk = None
            ia.base_item = item_map[ia.base_item.pk]
            ia.addon_category = category_map[ia.addon_category.pk]
            ia.save()

        for q in Quota.objects.filter(event=other, subevent__isnull=True).prefetch_related('items', 'variations'):
            items = list(q.items.all())
            vars = list(q.variations.all())
            q.pk = None
            q.event = self
            q.save()
            for i in items:
                if i.pk in item_map:
                    q.items.add(item_map[i.pk])
            for v in vars:
                q.variations.add(variation_map[v.pk])

        question_map = {}
        for q in Question.objects.filter(event=other).prefetch_related('items', 'options'):
            items = list(q.items.all())
            opts = list(q.options.all())
            question_map[q.pk] = q
            q.pk = None
            q.event = self
            q.save()

            for i in items:
                q.items.add(item_map[i.pk])
            for o in opts:
                o.pk = None
                o.question = q
                o.save()

        for cl in other.checkin_lists.filter(subevent__isnull=True).prefetch_related('limit_products'):
            items = list(cl.limit_products.all())
            cl.pk = None
            cl.event = self
            cl.save()
            for i in items:
                cl.limit_products.add(item_map[i.pk])

        for s in other.settings._objects.all():
            s.object = self
            s.pk = None
            if s.value.startswith('file://'):
                fi = default_storage.open(s.value[7:], 'rb')
                nonce = get_random_string(length=8)
                # TODO: make sure pub is always correct
                fname = 'pub/%s/%s/%s.%s.%s' % (
                    self.organizer.slug, self.slug, s.key, nonce, s.value.split('.')[-1]
                )
                newname = default_storage.save(fname, fi)
                s.value = 'file://' + newname
                s.save()
            elif s.key == 'tax_rate_default':
                try:
                    if int(s.value) in tax_map:
                        s.value = tax_map.get(int(s.value)).pk
                        s.save()
                    else:
                        s.delete()
                except ValueError:
                    s.delete()
            else:
                s.save()

        event_copy_data.send(
            sender=self, other=other,
            tax_map=tax_map, category_map=category_map, item_map=item_map, variation_map=variation_map,
            question_map=question_map
        )

    def get_payment_providers(self) -> dict:
        """
        Returns a dictionary of initialized payment providers mapped by their identifiers.
        """
        from ..signals import register_payment_providers

        responses = register_payment_providers.send(self)
        providers = {}
        for receiver, response in responses:
            if not isinstance(response, list):
                response = [response]
            for p in response:
                pp = p(self)
                providers[pp.identifier] = pp

        return OrderedDict(sorted(providers.items(), key=lambda v: str(v[1].verbose_name)))

    def get_invoice_renderers(self) -> dict:
        """
        Returns a dictionary of initialized invoice renderers mapped by their identifiers.
        """
        from ..signals import register_invoice_renderers

        responses = register_invoice_renderers.send(self)
        renderers = {}
        for receiver, response in responses:
            if not isinstance(response, list):
                response = [response]
            for p in response:
                pp = p(self)
                renderers[pp.identifier] = pp
        return renderers

    @property
    def invoice_renderer(self):
        """
        Returns the currently configured invoice renderer.
        """
        irs = self.get_invoice_renderers()
        return irs[self.settings.invoice_renderer]

    @property
    def active_subevents(self):
        """
        Returns a queryset of active subevents.
        """
        return self.subevents.filter(active=True).order_by('-date_from', 'name')

    @property
    def active_future_subevents(self):
        return self.subevents.filter(
            Q(active=True) & (
                Q(Q(date_to__isnull=True) & Q(date_from__gte=now()))
                | Q(date_to__gte=now())
            )
        ).order_by('date_from', 'name')

    @property
    def meta_data(self):
        data = {p.name: p.default for p in self.organizer.meta_properties.all()}
        data.update({v.property.name: v.value for v in self.meta_values.select_related('property').all()})
        return data

    def get_users_with_any_permission(self):
        """
        Returns a queryset of users who have any permission to this event.

        :return: Iterable of User
        """
        return self.get_users_with_permission(None)

    def get_users_with_permission(self, permission):
        """
        Returns a queryset of users who have a specific permission to this event.

        :return: Iterable of User
        """
        from .auth import User

        if permission:
            kwargs = {permission: True}
        else:
            kwargs = {}

        team_with_perm = Team.objects.filter(
            members__pk=OuterRef('pk'),
            organizer=self.organizer,
            **kwargs
        ).filter(
            Q(all_events=True) | Q(limit_events__pk=self.pk)
        )

        return User.objects.annotate(twp=Exists(team_with_perm)).filter(twp=True)

    def allow_delete(self):
        return not self.orders.exists() and not self.invoices.exists()


class SubEvent(EventMixin, LoggedModel):
    """
    This model represents a date within an event series.

    :param event: The event this belongs to
    :type event: Event
    :param active: Whether to show the subevent
    :type active: bool
    :param name: This event's full title
    :type name: str
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
    """

    event = models.ForeignKey(Event, related_name="subevents", on_delete=models.PROTECT)
    active = models.BooleanField(default=False, verbose_name=_("Active"),
                                 help_text=_("Only with this checkbox enabled, this date is visible in the "
                                             "frontend to users."))
    name = I18nCharField(
        max_length=200,
        verbose_name=_("Name"),
    )
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
    date_admission = models.DateTimeField(null=True, blank=True,
                                          verbose_name=_("Admission time"))
    presale_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("End of presale"),
        help_text=_("Optional. No products will be sold after this date. If you do not set this value, the presale "
                    "will end after the end date of your event."),
    )
    presale_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Start of presale"),
        help_text=_("Optional. No products will be sold before this date."),
    )
    location = I18nTextField(
        null=True, blank=True,
        max_length=200,
        verbose_name=_("Location"),
    )
    frontpage_text = I18nTextField(
        null=True, blank=True,
        verbose_name=_("Frontpage text")
    )

    items = models.ManyToManyField('Item', through='SubEventItem')
    variations = models.ManyToManyField('ItemVariation', through='SubEventItemVariation')

    class Meta:
        verbose_name = _("Date in event series")
        verbose_name_plural = _("Dates in event series")
        ordering = ("date_from", "name")

    def __str__(self):
        return '{} - {}'.format(self.name, self.get_date_range_display())

    @cached_property
    def settings(self):
        return self.event.settings

    @cached_property
    def item_price_overrides(self):
        from .items import SubEventItem

        return {
            si.item_id: si.price
            for si in SubEventItem.objects.filter(subevent=self, price__isnull=False)
        }

    @cached_property
    def var_price_overrides(self):
        from .items import SubEventItemVariation

        return {
            si.variation_id: si.price
            for si in SubEventItemVariation.objects.filter(subevent=self, price__isnull=False)
        }

    @property
    def meta_data(self):
        data = self.event.meta_data
        data.update({v.property.name: v.value for v in self.meta_values.select_related('property').all()})
        return data

    @property
    def currency(self):
        return self.event.currency

    def allow_delete(self):
        return self.event.subevents.count() > 1

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.cache.clear()


def generate_invite_token():
    return get_random_string(length=32, allowed_chars=string.ascii_lowercase + string.digits)


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

    def save(self, *args, **kwargs):
        created = not self.pk
        super().save(*args, **kwargs)
        if created:
            from .log import LogEntry
            from ..services.notifications import notify

            logentry = LogEntry.objects.create(
                content_object=self,
                action_type='pretix.event.action_required',
                event=self.event,
                visible=False
            )
            notify.apply_async(args=(logentry.pk,))


class EventMetaProperty(LoggedModel):
    """
    An organizer account can have EventMetaProperty objects attached to define meta information fields
    for its events. This information can be re-used for example in ticket layouts.

    :param organizer: The organizer this property is defined for.
    :type organizer: Organizer
    :param name: Name
    :type name: Name of the property, used in various places
    :param default: Default value
    :type default: str
    """
    organizer = models.ForeignKey(Organizer, related_name="meta_properties", on_delete=models.CASCADE)
    name = models.CharField(
        max_length=50, db_index=True,
        help_text=_(
            "Can not contain spaces or special characters except underscores"
        ),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9_]+$",
                message=_("The property name may only contain letters, numbers and underscores."),
            ),
        ],
        verbose_name=_("Name"),
    )
    default = models.TextField(blank=True)


class EventMetaValue(LoggedModel):
    """
    A meta-data value assigned to an event.

    :param event: The event this metadata is valid for
    :type event: Event
    :param property: The property this value belongs to
    :type property: EventMetaProperty
    :param value: The actual value
    :type value: str
    """
    event = models.ForeignKey('Event', on_delete=models.CASCADE,
                              related_name='meta_values')
    property = models.ForeignKey('EventMetaProperty', on_delete=models.CASCADE,
                                 related_name='event_values')
    value = models.TextField()

    class Meta:
        unique_together = ('event', 'property')

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.cache.clear()


class SubEventMetaValue(LoggedModel):
    """
    A meta-data value assigned to a sub-event.

    :param event: The event this metadata is valid for
    :type event: Event
    :param property: The property this value belongs to
    :type property: EventMetaProperty
    :param value: The actual value
    :type value: str
    """
    subevent = models.ForeignKey('SubEvent', on_delete=models.CASCADE,
                                 related_name='meta_values')
    property = models.ForeignKey('EventMetaProperty', on_delete=models.CASCADE,
                                 related_name='subevent_values')
    value = models.TextField()

    class Meta:
        unique_together = ('subevent', 'property')

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()
