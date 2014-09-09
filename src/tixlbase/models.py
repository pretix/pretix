from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class UserManager(BaseUserManager):
    """
    This is the user manager for our custom user model. See the User
    model documentation to see what's so special about our user model.
    """

    def create_user(self, email, password=None):
        user = self.model(email=email)
        user.set_password(user)
        user.save()
        return user

    def create_superuser(self, email, password=None):
        if password is None:
            raise Exception("You must provide a password")
        user = self.model(email=email)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(user)
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
    username = models.CharField(max_length=120)
    event = models.ForeignKey('Event', related_name="users",
                              null=True, blank=True)
    email = models.EmailField(unique=False, db_index=True,
                              null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    def __str__(self):
        return self.identifier

    def save(self, *args, **kwargs):
        if self.identifier is None:
            if self.event is None:
                self.identifier = self.email
            else:
                self.identifier = "%s@%d.event.tixl" % (self.username, self.event.id)
        super().save(*args, **kwargs)

    USERNAME_FIELD = 'identifier'
    REQUIRED_FIELDS = ['username']

    class Meta:
        unique_together = (("event", "username"),)


class Organizer(models.Model):
    """
    This model represents an entity organizing events, like a company,
    an organization or a person. It has one user as owner (who has
    registered it) and can have any number of users with admin
    authorization. Any organizer has a unique slug, which is a short
    name (alphanumeric, all lowercase) being used in URLs.
    """

    name = models.CharField(max_length=200)
    slug = models.CharField(max_length=50,
                            unique=True,
                            db_index=True)
    owner = models.ForeignKey(User, null=True, blank=True)

    class Meta:
        ordering = ("name",)


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

    organizer = models.ForeignKey(Organizer, related_name="events")
    name = models.CharField(max_length=200)
    slug = models.CharField(max_length=50,
                            db_index=True)
    locale = models.CharField(max_length=10)
    currency = models.CharField(max_length=10)
    date_from = models.DateTimeField()
    date_to = models.DateTimeField(null=True, blank=True)
    show_date_to = models.BooleanField(default=True)
    show_times = models.BooleanField(default=True)
    presale_end = models.DateTimeField(null=True, blank=True)
    presale_start = models.DateTimeField(null=True, blank=True)
    payment_term_days = models.IntegerField(default=14)
    payment_term_last = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("organizer", "slug"),)
        ordering = ("date_from", "name")
