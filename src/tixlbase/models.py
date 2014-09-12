from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.translation import ugettext_lazy as _
from django.template.defaultfilters import date as _date


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

    objects = UserManager()

    def __str__(self):
        return self.identifier

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

    def save(self, *args, **kwargs):
        if self.identifier is None:
            if self.event is None:
                self.identifier = self.email.lower()
            else:
                self.identifier = "%s@%d.event.tixl" % (self.username.lower(), self.event.id)
        if not self.pk:
            self.identifier = self.identifier.lower()
        super().save(*args, **kwargs)

    USERNAME_FIELD = 'identifier'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        unique_together = (("event", "username"),)


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

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Organizer")
        verbose_name_plural = _("Organizers")
        ordering = ("name",)


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

    def __str__(self):
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.organizer),
        }

    class Meta:
        verbose_name = _("Organizer permission")
        verbose_name_plural = _("Organizer permissions")
        unique_together = (("organizer", "user"),)


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
    slug = models.CharField(max_length=50, db_index=True,
                            verbose_name=_("Slug"))
    permitted = models.ManyToManyField(User, through='EventPermission',
                                       related_name="events",)
    locale = models.CharField(max_length=10,
                              choices=settings.LANGUAGES,
                              verbose_name=_("Default locale"))
    currency = models.CharField(max_length=10,
                                verbose_name=_("Default currency"))
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
    show_date_to = models.BooleanField(
        default=True,
        verbose_name=_("Show event end date")
    )
    show_times = models.BooleanField(
        default=True,
        verbose_name=_("Show dates with time")
    )
    presale_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("End of presale")
    )
    presale_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Start of presale")
    )
    payment_term_days = models.IntegerField(
        default=14,
        verbose_name=_("Payment term in days")
    )
    payment_term_last = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Last date of payments")
    )

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

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        unique_together = (("organizer", "slug"),)
        ordering = ("date_from", "name")


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

    def __str__(self):
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.event),
        }

    class Meta:
        verbose_name = _("Event permission")
        verbose_name_plural = _("Event permissions")
        unique_together = (("event", "user"),)
