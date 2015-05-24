from datetime import datetime
from itertools import product
import copy
import uuid
import random
import time
from django.core.urlresolvers import reverse

from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db.models import Q, Count
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.template.defaultfilters import date as _date
from django.core.validators import RegexValidator
from pretix.base.i18n import I18nCharField, I18nTextField
from pretix.base.settings import SettingsProxy
import six
from versions.models import Versionable as BaseVersionable
from versions.models import VersionedForeignKey, VersionedManyToManyField, get_utc_now

from .types import VariationDict


class Versionable(BaseVersionable):

    class Meta:
        abstract = True

    def clone_shallow(self, forced_version_date=None):
        """
        This behaves like clone(), but misses all the Many2Many-relation-handling. This is
        a performance optimization for cases in which we have to handle the Many2Many relations
        by handy anyways.
        """
        if not self.pk:
            raise ValueError('Instance must be saved before it can be cloned')

        if self.version_end_date:
            raise ValueError('This is a historical item and can not be cloned.')

        if forced_version_date:
            if not self.version_start_date <= forced_version_date <= get_utc_now():
                raise ValueError('The clone date must be between the version start date and now.')
        else:
            forced_version_date = get_utc_now()

        earlier_version = self

        later_version = copy.copy(earlier_version)
        later_version.version_end_date = None
        later_version.version_start_date = forced_version_date

        # set earlier_version's ID to a new UUID so the clone (later_version) can
        # get the old one -- this allows 'head' to always have the original
        # id allowing us to get at all historic foreign key relationships
        earlier_version.id = six.u(str(uuid.uuid4()))
        earlier_version.version_end_date = forced_version_date
        earlier_version.save()

        for field in earlier_version._meta.many_to_many:
            earlier_version.clone_relations_shallow(later_version, field.attname, forced_version_date)

        if hasattr(earlier_version._meta, 'many_to_many_related'):
            for rel in earlier_version._meta.many_to_many_related:
                earlier_version.clone_relations_shallow(later_version, rel.via_field_name, forced_version_date)

        later_version.save()

        return later_version

    def clone_relations_shallow(self, clone, manager_field_name, forced_version_date):
        # Source: the original object, where relations are currently pointing to
        source = getattr(self, manager_field_name)  # returns a VersionedRelatedManager instance
        # Destination: the clone, where the cloned relations should point to
        source.through.objects.filter(**{source.source_field.attname: clone.id}).update(**{
            source.source_field.attname: self.id, 'version_end_date': forced_version_date
        })


class UserManager(BaseUserManager):
    """
    This is the user manager for our custom user model. See the User
    model documentation to see what's so special about our user model.
    """

    def create_user(self, identifier, username, password=None):
        user = self.model(identifier=identifier)
        user.set_password(password)
        user.save()
        return user

    def create_global_user(self, email, password=None, **kwargs):
        user = self.model(**kwargs)
        user.identifier = email
        user.email = email
        user.set_password(password)
        user.save()
        return user

    def create_local_user(self, event, username, password=None, **kwargs):
        user = self.model(**kwargs)
        user.identifier = '%s@%s.event.pretix' % (username, event.identity)
        user.username = username
        user.event = event
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, identifier, password=None):
        if password is None:
            raise Exception("You must provide a password")
        user = self.model(identifier=identifier, email=identifier)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """
    This is the user model used by pretix for authentication.
    Handling users is somehow complicated, as we try to have two
    classes of users in one system:
        (1) We want *global* users who can just login into pretix and
            buy tickets for multiple events -- we also need those
            global users for event organizers who should not need
            multiple users for managing multiple events.
        (2) We want *local* users who exist only in the scope of a
            certain event
    The hard part is to find a primary key to identify all of these
    users. Letting the users choose usernames is a bad idea, as
    the primary key needs to be unique and there is no reason for a
    local user to block a name for all time. Using e-mail addresses
    is not a good idea either, for two reasons: First, a user might
    have multiple local users (so they are not unique), and second,
    it should be possible to create anonymous users without having
    to supply an e-mail address.
    Therefore, we use an abstract "identifier" field as the primary
    key. The identifier is:
        (1) the e-mail address for global users. An e-mail address
            is and should be required for them and global users use
            their e-mail address for login.
        (2) "{username}@{event.identity}.event.pretix" for local users, who
            use their username to login on the event page.
    The model's save() method automatically fills the identifier field
    according to this scheme when it is empty. The __str__() method
    returns the identifier.

    :param identifier: The identifier of the user, as described above
    :type identifier: str
    :param username: The username, null for global users.
    :type username: str
    :param event: The event the user belongs to, null for global users
    :type event: Event
    :param email: The user's e-mail address. May be empty or null for local users
    :type email: str
    :param givenname: The user's given name. May be empty or null.
    :type givenname: str
    :param familyname: The user's given name. May be empty or null.
    :type familyname: str
    :param givenname: The user's given name. May be empty or null.
    :type givenname: str
    :param is_active: Whether this user account is activated.
    :type is_active: bool
    :param is_staff: ``True`` for system operators.
    :type is_staff: bool
    :param date_joined: The datetime of the user's registration.
    :type date_joined: datetime
    :param locale: The user's preferred locale code.
    :type locale: str
    :param timezone: The user's preferred timezone.
    :type timezone: str
    """

    USERNAME_FIELD = 'identifier'
    REQUIRED_FIELDS = ['username']

    identifier = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=120, blank=True,
                                null=True,
                                help_text=_('Letters, digits and ./+/-/_ only.'))
    event = models.ForeignKey('Event', related_name="users",
                              null=True, blank=True,
                              on_delete=models.PROTECT)
    email = models.EmailField(unique=False, db_index=True,
                              null=True, blank=True,
                              verbose_name=_('E-mail'))
    givenname = models.CharField(max_length=255, blank=True,
                                 null=True,
                                 verbose_name=_('Given name'))
    familyname = models.CharField(max_length=255, blank=True,
                                  null=True,
                                  verbose_name=_('Family name'))
    is_active = models.BooleanField(default=True,
                                    verbose_name=_('Is active'))
    is_staff = models.BooleanField(default=False,
                                   verbose_name=_('Is site admin'))
    date_joined = models.DateTimeField(auto_now_add=True,
                                       verbose_name=_('Date joined'))
    locale = models.CharField(max_length=50,
                              choices=settings.LANGUAGES,
                              default=settings.LANGUAGE_CODE,
                              verbose_name=_('Language'))
    timezone = models.CharField(max_length=100,
                                default=settings.TIME_ZONE,
                                verbose_name=_('Timezone'))

    objects = UserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        unique_together = (("event", "username"),)

    def __str__(self):
        return self.identifier

    def save(self, *args, **kwargs):
        """
        Before passing the call to the default ``save()`` method, this will fill the ``identifier``
        field if it is empty, according to the scheme descriped in the model docstring.
        """
        if not self.identifier:
            if self.event is None:
                self.identifier = self.email.lower()
            else:
                self.identifier = "%s@%s.event.pretix" % (self.username.lower(), self.event.id)
        if not self.pk:
            self.identifier = self.identifier.lower()
        super().save(*args, **kwargs)

    def get_short_name(self) -> str:
        """
        Returns the first of the following user properties that is found to exist:

        * Given name
        * Family name
        * User name
        * E-mail address
        """
        if self.givenname:
            return self.givenname
        elif self.familyname:
            return self.familyname
        else:
            return self.get_local_name()

    def get_full_name(self) -> str:
        """
        Returns the first of the following user properties that is found to exist:

        * A combination of given name and family name, depending on the locale
        * Given name
        * Family name
        * User name
        * E-mail address
        """
        if self.givenname and not self.familyname:
            return self.givenname
        elif not self.givenname and self.familyname:
            return self.familyname
        elif self.familyname and self.givenname:
            return _('%(family)s, %(given)s') % {
                'family': self.familyname,
                'given': self.givenname
            }
        else:
            return self.get_local_name()

    def get_local_name(self) -> str:
        """
        Returns the username for local users and the e-mail address for global
        users.
        """
        if self.username:
            return self.username
        if self.email:
            return self.email
        return self.identifier


class Organizer(Versionable):
    """
    This model represents an entity organizing events, e.g. a company, institution,
    charity, person, …

    :param name: The organizer's name
    :type name: str
    :param slug: A globally unique, short name for this organizer, to be used
                 in URLs and similar places.
    :type slug: str
    """

    name = models.CharField(max_length=200,
                            verbose_name=_("Name"))
    slug = models.SlugField(max_length=50,
                            db_index=True,
                            verbose_name=_("Slug"))
    permitted = models.ManyToManyField(User, through='OrganizerPermission',
                                       related_name="organizers")

    class Meta:
        verbose_name = _("Organizer")
        verbose_name_plural = _("Organizers")
        ordering = ("name",)

    def __str__(self):
        return self.name

    @cached_property
    def settings(self) -> SettingsProxy:
        """
        Returns an object representing this organizer's settings
        """
        return SettingsProxy(self, type=OrganizerSetting)


class OrganizerPermission(Versionable):
    """
    The relation between an Organizer and an User who has permissions to
    access an organizer profile.

    :param organizer: The organizer this relation refers to
    :type organizer: Organizer
    :param user: The user this set of permissions is valid for
    :type user: User
    :param can_create_events: Whether or not this user can create new events with this
                              organizer account.
    :type can_create_events: bool
    """

    organizer = VersionedForeignKey(Organizer)
    user = models.ForeignKey(User, related_name="organizer_perms")
    can_create_events = models.BooleanField(
        default=True,
        verbose_name=_("Can create events"),
    )

    class Meta:
        verbose_name = _("Organizer permission")
        verbose_name_plural = _("Organizer permissions")

    def __str__(self):
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.organizer),
        }


class Event(Versionable):
    """
    This model represents an event. An event is anything you can buy
    tickets for.

    :param organizer: The organizer this event belongs to
    :type organizer: Organizer
    :param name: This events full title
    :type name: str
    :param slug: A short, alphanumeric, all-lowercase name for use in URLs. The slug has to
                 be unique among the events of the same organizer.
    :type slug: str
    :param currency: The currency of all prices and payments of this event
    :type currency: str
    :param date_from: The datetime this event starts
    :type date_from: datetime
    :param date_to: The datetime this event ends
    :type date_to: datetime
    :param presale_start: No tickets will be sold before this date.
    :type presale_start: datetime
    :param presale_end: No tickets will be sold before this date.
    :type presale_end: datetime
    :param plugins: A comma-separated list of plugin names that are active for this
                    event.
    :type plugins: str
    """

    organizer = VersionedForeignKey(Organizer, related_name="events",
                                    on_delete=models.PROTECT)
    name = I18nCharField(
        max_length=200,
        verbose_name=_("Name"),
    )
    slug = models.SlugField(
        max_length=50, db_index=True,
        help_text=_(
            "Should be short, only contain lowercase letters and numbers, and must be unique among your events. "
            + "This is being used in addresses and bank transfer references."),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9.-]+$",
                message=_("The slug may only contain letters, numbers, dots and dashes."),
            )
        ],
        verbose_name=_("Slug"),
    )
    permitted = models.ManyToManyField(User, through='EventPermission',
                                       related_name="events",)
    currency = models.CharField(max_length=10,
                                verbose_name=_("Default currency"),
                                default=settings.DEFAULT_CURRENCY)
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
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
        # unique_together = (("organizer", "slug"),)  # TODO: Enforce manually
        ordering = ("date_from", "name")

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)
        self.get_cache().clear()
        return obj

    def get_plugins(self) -> "list[str]":
        """
        Get the names of the plugins activated for this event as a list.
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

    def get_cache(self) -> "pretix.base.cache.EventRelatedCache":
        """
        Returns an :py:class:`EventRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this event, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the event or one of its related objects change.
        """
        from pretix.base.cache import EventRelatedCache
        return EventRelatedCache(self)

    @cached_property
    def settings(self):
        """
        Returns an object representing this event's settings
        """
        return SettingsProxy(self, type=EventSetting, parent=self.organizer)

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


class EventPermission(Versionable):
    """
    The relation between an Event and an User who has permissions to
    access an event.

    :param event: The event this refers to
    :type event: Event
    :param user: The user these permission set applies to
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

    event = VersionedForeignKey(Event)
    user = models.ForeignKey(User, related_name="event_perms")
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
    can_change_orders = models.BooleanField(
        default=True,
        verbose_name=_("Can change orders")
    )

    class Meta:
        verbose_name = _("Event permission")
        verbose_name_plural = _("Event permissions")

    def __str__(self):
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.event),
        }


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

    def __lt__(self, other):
        if self.position < other.position:
            return True
        if self.position == other.position:
            return self.pk < other.pk
        return False


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
        related_name="properties",
    )
    name = I18nCharField(
        max_length=250,
        verbose_name=_("Property name"),
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
        ordering = ("position",)

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
    def sortkey(self):
        return self.position, self.pk

    def __lt__(self, other):
        return self.sortkey < other.sortkey


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
        related_name="questions",
    )
    question = I18nTextField(
        verbose_name=_("Question"),
    )
    type = models.CharField(
        max_length=5,
        choices=TYPE_CHOICES,
        verbose_name=_("Question type"),
    )
    required = models.BooleanField(
        default=False,
        verbose_name=_("Required question"),
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
    :param short_description: A short description
    :type short_description: str
    :param long_description: A long description
    :type long_description: str
    :param default_price: The item's default price
    :type default_price: decimal.Decimal
    :param tax_rate: The VAT tax that is included in this item's price (in %)
    :type tax_rate: decimal.Decimal
    :param properties: A set of ``Property`` objects that should be applied to this item
    :param questions: A set of ``Question`` objects that should be applied to this item
    :param admission: ``True``, if this item allows persons to enter the event (as opposed to e.g. merchandise)
    :type admission: bool

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
    short_description = I18nTextField(
        verbose_name=_("Short description"),
        help_text=_("This is shown below the product name in lists."),
        null=True, blank=True,
    )
    long_description = I18nTextField(
        verbose_name=_("Long description"),
        null=True, blank=True,
    )
    default_price = models.DecimalField(
        null=True, blank=True,
        verbose_name=_("Default price"),
        max_digits=7, decimal_places=2
    )
    tax_rate = models.DecimalField(
        null=True, blank=True,
        verbose_name=_("Taxes included in percent"),
        max_digits=7, decimal_places=2
    )
    properties = VersionedManyToManyField(
        Property,
        related_name='items',
        verbose_name=_("Properties"),
        blank=True,
        help_text=_(
            'The selected properties will be available for the user '
            'to select. After saving this field, move to the '
            '\'Variations\' tab to configure the details.'
        )
    )
    questions = VersionedManyToManyField(
        Question,
        related_name='items',
        verbose_name=_("Questions"),
        blank=True,
        help_text=_(
            'The user will be asked to fill in answers for the '
            'selected questions'
        )
    )
    admission = models.BooleanField(
        verbose_name=_("Is an admission ticket"),
        help_text=_(
            'Whether or not buying this product allows a person to enter '
            'your event'
        ),
        default=False
    )

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

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

    def get_all_variations(self, use_cache: bool=False) -> "list[VariationDict]":
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

        from .signals import determine_availability

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

            for receiver, response in responses:
                if 'available' in response[i]:
                    var['available'] &= response[i]['available']
                if 'price' in response[i] and response[i]['price'] \
                        and response[i]['price'] < var['price']:
                    var['price'] = response[i]['price']

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
        return min([q.availability() for q in self.quotas.all()])

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
        from .signals import determine_availability
        vd = VariationDict()
        responses = determine_availability.send(
            self.event, item=self,
            variations=[vd], context=None,
            cache=self.event.get_cache()
        )
        price = self.default_price
        for receiver, response in responses:
            if 'available' in response[0] and not response[0]['available']:
                return False
            elif 'price' in response[0] and response[0]['price'] < price:
                price = response[0]['price']
        return price


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

    def check_quotas(self):
        """
        This method is used to determine whether this ItemVariation is currently
        available for sale in terms of quotas.

        :returns: any of the return codes of :py:meth:`Quota.availability()`.
        """
        return min([q.availability() for q in self.quotas.all()])

    def to_variation_dict(self):
        """
        :return: a :py:class:`VariationDict` representing this variation.
        """
        vd = VariationDict()
        for v in self.values.all():
            vd[v.prop.identity] = v
        vd['variation'] = self
        return vd

    def check_restrictions(self):
        """
        This method is used to determine whether this ItemVariation is restricted
        in sale by any restriction plugins.

        :returns:

            * ``False``, if the item is unavailable
            * the item's price, otherwise
        """
        from .signals import determine_availability
        responses = determine_availability.send(
            self.item.event, item=self.item,
            variations=[self.to_variation_dict()], context=None,
            cache=self.item.event.get_cache()
        )
        price = self.default_price if self.default_price is not None else self.item.default_price
        for receiver, response in responses:
            if 'available' in response[0] and not response[0]['available']:
                return False
            elif 'price' in response[0] and response[0]['price'] < price:
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
        from pretix.control.views.forms import VariationsField as FVariationsField
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
        verbose_name=_("Total capacity")
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
    locked = models.DateTimeField(
        null=True, blank=True
    )
    locked_here = False

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

    def availability(self):
        """
        This method is used to determine whether Items or ItemVariations belonging
        to this quota should currently be available for sale.

        :returns: a tuple where the first entry is one of the Quota.AVAILABILITY_ constants and the second
                  is the number of available tickets.
        """
        # TODO: These lookups are highly inefficient. However, we'll wait with optimizing
        #       until Django 1.8 is released, as the following feature might make it a
        #       lot easier:
        #       https://docs.djangoproject.com/en/1.8/ref/models/conditional-expressions/
        # TODO: Test for interference with old versions of Item-Quota-relations, etc.
        # TODO: Prevent corner-cases like people having ordered an item before it got
        #       its first variationsadded
        quotalookup = (
            (  # Orders for items which do not have any variations
                Q(variation__isnull=True)
                & Q(item__quotas__in=[self])
            ) | (  # Orders for items which do have any variations
                Q(variation__quotas__in=[self])
            )
        )

        paid_orders = OrderPosition.objects.current.filter(
            Q(order__status=Order.STATUS_PAID)
            & quotalookup
        ).count()

        if paid_orders >= self.size:
            return Quota.AVAILABILITY_GONE, 0

        pending_valid_orders = OrderPosition.objects.current.filter(
            Q(order__status=Order.STATUS_PENDING)
            & Q(order__expires__gte=now())
            & quotalookup
        ).count()
        if (paid_orders + pending_valid_orders) >= self.size:
            return Quota.AVAILABILITY_ORDERED, 0

        valid_cart_positions = CartPosition.objects.current.filter(
            Q(expires__gte=now())
            & quotalookup
        ).count()
        if (paid_orders + pending_valid_orders + valid_cart_positions) >= self.size:
            return Quota.AVAILABILITY_RESERVED, 0

        return Quota.AVAILABILITY_OK, self.size - paid_orders - pending_valid_orders - valid_cart_positions

    class LockTimeoutException(Exception):
        pass

    class QuotaExceededException(Exception):
        pass

    def lock(self):
        """
        Issue a lock on this quota so nobody can take tickets from this quota until
        you release the lock. Will retry 5 times on failure.

        :raises Quota.LockTimeoutException: if the quota is locked every time we try to obtain the lock
        """
        retries = 5
        for i in range(retries):
            dt = now()
            updated = Quota.objects.current.filter(
                identity=self.identity, locked__isnull=True,
                version_end_date__isnull=True
            ).update(
                locked=dt
            )
            if updated:
                self.locked_here = dt
                self.locked = dt
                return True
            time.sleep(2 ** i / 100)
        raise Quota.LockTimeoutException()

    def release(self, force=False):
        """
        Release a lock placed by :py:meth:`lock()`. If the parameter force is not set to ``True``,
        the lock will only be released if it was issued in _this_ python
        representation of the database object.
        """
        if not self.locked_here and not force:
            return False
        updated = Quota.objects.current.filter(
            identity=self.identity,
            version_end_date__isnull=True
        ).update(
            locked=None
        )
        self.locked_here = None
        self.locked = None
        return updated


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
    :param user: The user who ordered this
    :type user: User
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
    user = models.ForeignKey(
        User, null=True, blank=True,
        verbose_name=_("User"),
        related_name="orders"
    )
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

    def str(self):
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
    def can_modify_answers(self):
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

    def _can_be_paid(self, keep_locked=False):
        error_messages = {
            'late': _("The payment is too late to be accepted."),
        }

        if self.event.settings.get('payment_term_last') \
                and now() > self.event.settings.get('payment_term_last'):
            return error_messages['late'], None
        if now() < self.expires:
            return True, None
        if not self.event.settings.get('payment_term_accept_late'):
            return error_messages['late'], None

        return self._is_still_available(keep_locked)

    def _is_still_available(self, keep_locked=False):
        error_messages = {
            'unavailable': _('Some of the ordered products were no longer available.'),
            'busy': _('We were not able to process the request completely as the '
                      'server was too busy. Please try again.'),
        }
        positions = list(self.positions.all().select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation__values', 'variation__values__prop',
            'item__questions', 'answers'
        ))
        quotas_locked = set()
        release = True

        try:
            for i, op in enumerate(positions):
                quotas = list(op.item.quotas.all()) if op.variation is None else list(op.variation.quotas.all())
                if len(quotas) == 0:
                    raise Quota.QuotaExceededException(error_messages['unavailable'])

                for quota in quotas:
                    # Lock the quota, so no other thread is allowed to perform sales covered by this
                    # quota while we're doing so.
                    if quota not in quotas_locked:
                        quota.lock()
                        quotas_locked.add(quota)
                        quota.cached_availability = quota.availability()[1]
                    else:
                        # Use cached version
                        quota = [q for q in quotas_locked if q.pk == quota.pk][0]
                    quota.cached_availability -= 1
                    if quota.cached_availability < 0:
                        # This quota is sold out/currently unavailable, so do not sell this at all
                        raise Quota.QuotaExceededException(error_messages['unavailable'])
        except Quota.QuotaExceededException as e:
            return str(e), None
        except Quota.LockTimeoutException:
            # Is raised when there are too many threads asking for quota locks and we were
            # unaible to get one
            return error_messages['busy'], None
        else:
            release = False
        finally:
            # Release the locks. This is important ;)
            if release or not keep_locked:
                for quota in quotas_locked:
                    quota.release()
        return True, quotas_locked

    def mark_paid(self, provider=None, info=None, date=None, manual=None, force=False):
        """
        Mark this order as paid. This clones the order object, sets the payment provider,
        info and date and returns the cloned order object.

        :param provider: The payment provider that marked this as paid
        :type provider: str
        :param info: The information to store in order.payment_info
        :type info: str
        :param date: The date the payment was received (if you pass ``None``, the current
                     time will be used).
        :type date: datetime
        :param force: Whether this payment should be marked as paid even if no remaining
                      quota is available (default: ``False``).
        :type force: boolean
        :raises Quota.QuotaExceededException: if the quota is exceeded and ``force`` is ``False``
        """
        can_be_paid, quotas_locked = self._can_be_paid(keep_locked=True)
        if not force and can_be_paid is not True:
            raise Quota.QuotaExceededException(can_be_paid)
        order = self.clone()
        order.payment_provider = provider or order.payment_provider
        order.payment_info = info or order.payment_info
        order.payment_date = date or now()
        if manual is not None:
            order.payment_manual = manual
        order.status = Order.STATUS_PAID
        order.save()

        if quotas_locked:
            for quota in quotas_locked:
                quota.release()

        from pretix.base.mail import mail
        mail(
            order.user, _('Payment received for your order: %(code)s') % {'code': order.code},
            'pretixpresale/email/order_paid.txt',
            {
                'user': order.user,
                'order': order,
                'event': order.event,
                'url': settings.SITE_URL + reverse('presale:event.order', kwargs={
                    'event': order.event.slug,
                    'organizer': order.event.organizer.slug,
                    'order': order.code
                }),
                'downloads': order.event.settings.get('ticket_download', as_type=bool)
            },
            order.event
        )
        return order


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
    def transform_cart_positions(cls, cp: list, order) -> list:
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
    :param user: The user who has this in his cart
    :type user: User
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
    user = models.ForeignKey(
        User, null=True, blank=True,
        verbose_name=_("User")
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


class EventSetting(Versionable):
    """
    An event settings is a key-value setting which can be set for a
    specific event
    """
    object = VersionedForeignKey(Event, related_name='setting_objects')
    key = models.CharField(max_length=255)
    value = models.TextField()


class OrganizerSetting(Versionable):
    """
    An event option is a key-value setting which can be set for an
    organizer. It will be inherited by the events of this organizer
    """
    object = VersionedForeignKey(Organizer, related_name='setting_objects')
    key = models.CharField(max_length=255)
    value = models.TextField()
