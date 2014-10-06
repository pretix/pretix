from itertools import product

from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.translation import ugettext_lazy as _
from django.template.defaultfilters import date as _date
from django.core.validators import RegexValidator


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

    def create_superuser(self, identifier, username, password=None):
        if password is None:
            raise Exception("You must provide a password")
        user = self.model(identifier=identifier, username=username)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """
    This is the user model used by tixl for authentication.
    Handling users is somehow complicated, as we try to have two
    classes of users in one system:
        (1) We want global users who can just login into tixl and
            buy tickets for multiple events -- we also need those
            global users for event organizers who should not need
            multiple users for managing multiple events.
        (2) We want local users who exist only in the scope of a
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
        (2) "{username}@{event.id}.event.tixl" for local users, who
            use their username to login on the event page.
    The model's save() method automatically fills the identifier field
    according to this scheme when it is empty. The __str__() method
    returns the identifier.

    The is_staff field is only True for system operators.
    """

    USERNAME_FIELD = 'identifier'
    REQUIRED_FIELDS = ['username']

    identifier = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=120, blank=True,
                                null=True,
                                help_text=_('Letters, digits and @/./+/-/_ only.'))
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
                                   verbose_name=('Is site admin'))
    date_joined = models.DateTimeField(auto_now_add=True,
                                       verbose_name=_('Date joined'))
    locale = models.CharField(max_length=50,
                              choices=settings.LANGUAGES,
                              default=settings.LANGUAGE_CODE,
                              verbose_name=_('Language'))
    timezone = models.CharField(max_length=100,
                                default=settings.TIME_ZONE,
                                verbose_name=('Timezone'))

    objects = UserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        unique_together = (("event", "username"),)

    def __str__(self):
        return self.identifier

    def save(self, *args, **kwargs):
        if self.identifier is None:
            if self.event is None:
                self.identifier = self.email.lower()
            else:
                self.identifier = "%s@%d.event.tixl" % (self.username.lower(), self.event.id)
        if not self.pk:
            self.identifier = self.identifier.lower()
        super().save(*args, **kwargs)

    def get_short_name(self):
        if self.givenname:
            return self.givenname
        elif self.familyname:
            return self.familyname
        else:
            return self.username

    def get_full_name(self):
        if self.givenname and not self.familyname:
            return self.givenname
        elif not self.givenname and self.familyname:
            return self.familyname
        elif self.familyname and self.givenname:
            return '%(family)s, %(given)s' % {
                'family': self.familyname,
                'given': self.givenname
            }
        else:
            return self.username


class Organizer(models.Model):
    """
    This model represents an entity organizing events, like a company.
    Any organizer has a unique slug, which is a short name (alphanumeric,
    all lowercase) being used in URLs.
    """

    name = models.CharField(max_length=200,
                            verbose_name=_("Name"))
    slug = models.CharField(max_length=50,
                            unique=True, db_index=True,
                            verbose_name=_("Slug"))
    permitted = models.ManyToManyField(User, through='OrganizerPermission',
                                       related_name="organizers")

    class Meta:
        verbose_name = _("Organizer")
        verbose_name_plural = _("Organizers")
        ordering = ("name",)

    def __str__(self):
        return self.name


class OrganizerPermission(models.Model):
    """
    The relation between an Organizer and an User who has permissions to
    access an organizer profile.
    """

    organizer = models.ForeignKey(Organizer)
    user = models.ForeignKey(User, related_name="organizer_perms")
    can_create_events = models.BooleanField(
        default=True,
        verbose_name=_("Can create events"),
    )

    class Meta:
        verbose_name = _("Organizer permission")
        verbose_name_plural = _("Organizer permissions")
        unique_together = (("organizer", "user"),)

    def __str__(self):
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.organizer),
        }


class Event(models.Model):
    """
    This model represents an event. An event is anything you can buy
    tickets for. It belongs to one orgnaizer and has a name and a slug,
    the latter being a short, alphanumeric, all-lowercase name being
    used in URLs. The slug has to be unique among the events of the same
    organizer.

    An event can hold several properties, such as a default locale and
    currency.

    The event has date_from and date_to field which mark the actual
    datetime of the event itself. The show_date_to and show_times
    fields are used to control the display of these dates. (Without
    show_times only days are shown, now times.)

    The presale_start and presale_end fields mark the time frame in
    which tickets are sold for this event. These two dates override
    every other restrictions to ticket sale if set.

    The payment_term_days field holds the number of days after
    submitting a ticket order, in which the ticket has to be paid.
    The payment_term_last is the day all orders must be paid by, no
    matter when they were ordered (and thus, ignoring payment_term_days).
    """

    organizer = models.ForeignKey(Organizer, related_name="events",
                                  on_delete=models.PROTECT)
    name = models.CharField(max_length=200,
                            verbose_name=_("Name"))
    slug = models.CharField(
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
    locale = models.CharField(max_length=10,
                              choices=settings.LANGUAGES,
                              verbose_name=_("Default locale"))
    timezone = models.CharField(max_length=100,
                                default=settings.TIME_ZONE,
                                verbose_name=_('Default timezone'))
    currency = models.CharField(max_length=10,
                                verbose_name=_("Default currency"))
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
    show_date_to = models.BooleanField(
        default=True,
        verbose_name=_("Show event end date"),
        help_text=_("If disabled, only event's start date will be displayed to the public."),
    )
    show_times = models.BooleanField(
        default=True,
        verbose_name=_("Show dates with time"),
        help_text=_("If disabled, the event's start and end date will be displayed without the time of day."),
    )
    presale_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("End of presale"),
        help_text=_("No items will be sold after this date."),
    )
    presale_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Start of presale"),
        help_text=_("No items will be sold before this date."),
    )
    payment_term_days = models.IntegerField(
        default=14,
        verbose_name=_("Payment term in days"),
        help_text=_("The number of days after placing an order the user has to pay to preserve his reservation."),
    )
    payment_term_last = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Last date of payments"),
        help_text=_("The last date any payments are accepted. This has precedence over the number of days configured above.")
    )

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        unique_together = (("organizer", "slug"),)
        ordering = ("date_from", "name")

    def __str__(self):
        return self.name

    def get_date_from_display(self):
        return _date(
            self.date_from,
            "DATETIME_FORMAT" if self.show_times else "DATE_FORMAT"
        )

    def get_date_to_display(self):
        if not self.show_date_to:
            return ""
        return _date(
            self.date_to,
            "DATETIME_FORMAT" if self.show_times else "DATE_FORMAT"
        )


class EventPermission(models.Model):
    """
    The relation between an Event and an User who has permissions to
    access an event.
    """

    event = models.ForeignKey(Event)
    user = models.ForeignKey(User, related_name="event_perms")
    can_change_settings = models.BooleanField(
        default=True,
        verbose_name=_("Can change event settings")
    )
    can_change_items = models.BooleanField(
        default=True,
        verbose_name=_("Can change item settings")
    )

    class Meta:
        verbose_name = _("Event permission")
        verbose_name_plural = _("Event permissions")
        unique_together = (("event", "user"),)

    def __str__(self):
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.event),
        }


class ItemCategory(models.Model):
    """
    Items can be sorted into categories
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='categories',
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("Category name"),
    )
    position = models.IntegerField(
        default=0
    )

    class Meta:
        verbose_name = _("Item category")
        verbose_name_plural = _("Item categories")
        ordering = ('position',)

    def __str__(self):
        return self.name


class Property(models.Model):
    """
    A property is a modifier which can be applied to an
    Item. For example 'Size' would be a property associated
    with the item 'T-Shirt'.
    """

    event = models.ForeignKey(
        Event,
        related_name="properties",
    )
    name = models.CharField(
        max_length=250,
        verbose_name=_("Property name"),
    )

    class Meta:
        verbose_name = _("Item property")
        verbose_name_plural = _("Item properties")

    def __str__(self):
        return self.name


class PropertyValue(models.Model):
    """
    A value of a property. If the property would be 'T-Shirt size',
    this could be 'M' or 'L'
    """

    prop = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="values"
    )
    value = models.CharField(
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


class Question(models.Model):
    """
    A question is an input field that can be used to extend a ticket
    by custom information, e.g. "Attendee name" or "Attendee age".
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

    event = models.ForeignKey(
        Event,
        related_name="questions",
    )
    question = models.TextField(
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
        return self.question


class Item(models.Model):
    """
    An item is a thing which can be sold. It belongs to an
    event and may or may not belong to a category.

    It has a default price which might by overriden by
    restrictions.

    Items can not be deleted, as this would cause database
    inconsistencies. Instead, they have an attribute "deleted".
    Deleted items will not be shown anywhere.
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
    name = models.CharField(
        max_length=255,
        verbose_name=_("Item name")
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    deleted = models.BooleanField(default=False)
    short_description = models.TextField(
        verbose_name=_("Short description"),
        help_text=_("This is shown below the item name in lists."),
        null=True, blank=True,
    )
    long_description = models.TextField(
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
    properties = models.ManyToManyField(
        Property,
        related_name='items',
        verbose_name=_("Properties"),
        blank=True,
        help_text=_(
            'The selected properties will be available for the user '
            + 'to select. After saving this field, move to the '
            + '\'Variations\' tab to configure the details.'
        )
    )
    questions = models.ManyToManyField(
        Question,
        related_name='items',
        verbose_name=_("Questions"),
        blank=True,
        help_text=_(
            'The user will be asked to fill in answers for the '
            + 'selected questions'
        )
    )

    class Meta:
        verbose_name = _("Item")
        verbose_name_plural = _("Items")

    def __str__(self):
        return self.name

    def delete(self):
        self.deleted = True
        self.active = False
        return super().save()

    def get_all_variations(self):
        """
        This method returns a list containing all variations of this
        item. The list contains one dictionary per variation, where
        the Proprty IDs are keys and the PropertyValue objects are
        values. If an ItemVariation object exists, it is available in
        the dictionary via the special key 'variation'.
        """
        all_variations = self.variations.all().prefetch_related("values")
        all_properties = self.properties.all().prefetch_related("values")
        variations_cache = {}
        for var in all_variations:
            key = []
            for v in var.values.all():
                key.append((v.prop_id, v.pk))
            key = hash(tuple(sorted(key)))
            variations_cache[key] = var

        result = []
        for comb in product(*[prop.values.all() for prop in all_properties]):
            if len(comb) == 0:
                result.append({})
                continue
            key = []
            var = {}
            for v in comb:
                key.append((v.prop.pk, v.pk))
                var[v.prop.pk] = v
            key = hash(tuple(sorted(key)))
            if key in variations_cache:
                var['variation'] = variations_cache[key]
            result.append(var)

        return result


class ItemVariation(models.Model):
    """
    A variation is an item combined with values for all properties
    associated with the item. For example, if your item is 'T-Shirt'
    and your properties are 'Size' and 'Color', then an example for a
    variation would be 'T-Shirt XL read'.

    Attention: _ALL_ combinations of PropertyValues _ALWAYS_ exist,
    even if there is no ItemVariation object for them! ItemVariation objects
    do NOT prove existance, they are only available to make it possible
    to override default values (like the price) for certain combinations
    of property values.

    They also allow to explicitly EXCLUDE certain combinations of property
    values by creating an ItemVariation object for them with active set to
    False.

    Restrictions can be not only set to items but also directly to variations.
    """
    item = models.ForeignKey(
        Item,
        related_name='variations'
    )
    values = models.ManyToManyField(
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
        verbose_name = _("Item variation")
        verbose_name_plural = _("Item variations")
