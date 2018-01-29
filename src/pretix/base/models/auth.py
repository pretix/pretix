from typing import Union

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin,
)
from django.contrib.auth.tokens import default_token_generator
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _
from django_otp.models import Device

from pretix.base.i18n import language
from pretix.helpers.urls import build_absolute_uri

from .base import LoggingMixin


class UserManager(BaseUserManager):
    """
    This is the user manager for our custom user model. See the User
    model documentation to see what's so special about our user model.
    """

    def create_user(self, email: str, password: str=None, **kwargs):
        user = self.model(email=email, **kwargs)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email: str, password: str=None):  # NOQA
        # Not used in the software but required by Django
        if password is None:
            raise Exception("You must provide a password")
        user = self.model(email=email)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        return user


def generate_notifications_token():
    return get_random_string(length=32)


class User(AbstractBaseUser, PermissionsMixin, LoggingMixin):
    """
    This is the user model used by pretix for authentication.

    :param email: The user's email address, used for identification.
    :type email: str
    :param fullname: The user's full name. May be empty or null.
    :type fullname: str
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

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    email = models.EmailField(unique=True, db_index=True, null=True, blank=True,
                              verbose_name=_('E-mail'))
    fullname = models.CharField(max_length=255, blank=True, null=True,
                                verbose_name=_('Full name'))
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
    require_2fa = models.BooleanField(
        default=False,
        verbose_name=_('Two-factor authentification is required to log in')
    )
    notifications_send = models.BooleanField(
        default=True,
        verbose_name=_('Receive notifications according to my settings below'),
        help_text=_('If turned off, you will not get any notifications.')
    )
    notifications_token = models.CharField(max_length=255, default=generate_notifications_token)

    objects = UserManager()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._teamcache = {}

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    def get_short_name(self) -> str:
        """
        Returns the first of the following user properties that is found to exist:

        * Full name
        * Email address

        Only present for backwards compatibility
        """
        if self.fullname:
            return self.fullname
        else:
            return self.email

    def get_full_name(self) -> str:
        """
        Returns the first of the following user properties that is found to exist:

        * Full name
        * Email address
        """
        if self.fullname:
            return self.fullname
        else:
            return self.email

    def send_security_notice(self, messages, email=None):
        from pretix.base.services.mail import mail, SendMailException

        try:
            with language(self.locale):
                msg = '- ' + '\n- '.join(str(m) for m in messages)

            mail(
                email or self.email,
                _('Account information changed'),
                'pretixcontrol/email/security_notice.txt',
                {
                    'user': self,
                    'messages': msg,
                    'url': build_absolute_uri('control:user.settings')
                },
                event=None,
                locale=self.locale
            )
        except SendMailException:
            pass  # Already logged

    def send_password_reset(self):
        from pretix.base.services.mail import mail

        mail(
            self.email, _('Password recovery'), 'pretixcontrol/email/forgot.txt',
            {
                'user': self,
                'url': (build_absolute_uri('control:auth.forgot.recover')
                        + '?id=%d&token=%s' % (self.id, default_token_generator.make_token(self)))
            },
            None, locale=self.locale
        )

    @property
    def all_logentries(self):
        from pretix.base.models import LogEntry

        return LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(User),
                                       object_id=self.pk)

    def _get_teams_for_organizer(self, organizer):
        if 'o{}'.format(organizer.pk) not in self._teamcache:
            self._teamcache['o{}'.format(organizer.pk)] = list(self.teams.filter(organizer=organizer))
        return self._teamcache['o{}'.format(organizer.pk)]

    def _get_teams_for_event(self, organizer, event):
        if 'e{}'.format(event.pk) not in self._teamcache:
            self._teamcache['e{}'.format(event.pk)] = list(self.teams.filter(organizer=organizer).filter(
                Q(all_events=True) | Q(limit_events=event)
            ))
        return self._teamcache['e{}'.format(event.pk)]

    class SuperuserPermissionSet:
        def __contains__(self, item):
            return True

    def get_event_permission_set(self, organizer, event) -> Union[set, SuperuserPermissionSet]:
        """
        Gets a set of permissions (as strings) that a user holds for a particular event

        :param organizer: The organizer of the event
        :param event: The event to check
        :return: set in case of a normal user and a SuperuserPermissionSet in case of a superuser (fake object where
                 a in b always returns true).
        """
        if self.is_superuser:
            return self.SuperuserPermissionSet()

        teams = self._get_teams_for_event(organizer, event)
        return set.union(*[t.permission_set() for t in teams])

    def get_organizer_permission_set(self, organizer) -> Union[set, SuperuserPermissionSet]:
        """
        Gets a set of permissions (as strings) that a user holds for a particular organizer

        :param organizer: The organizer of the event
        :return: set in case of a normal user and a SuperuserPermissionSet in case of a superuser (fake object where
                 a in b always returns true).
        """
        if self.is_superuser:
            return self.SuperuserPermissionSet()

        teams = self._get_teams_for_organizer(organizer)
        return set.union(*[t.permission_set() for t in teams])

    def has_event_permission(self, organizer, event, perm_name=None) -> bool:
        """
        Checks if this user is part of any team that grants access of type ``perm_name``
        to the event ``event``.

        :param organizer: The organizer of the event
        :param event: The event to check
        :param perm_name: The permission, e.g. ``can_change_teams``
        :return: bool
        """
        if self.is_superuser:
            return True
        teams = self._get_teams_for_event(organizer, event)
        if teams:
            self._teamcache['e{}'.format(event.pk)] = teams
            if not perm_name or any([team.has_permission(perm_name) for team in teams]):
                return True
        return False

    def has_organizer_permission(self, organizer, perm_name=None):
        """
        Checks if this user is part of any team that grants access of type ``perm_name``
        to the organizer ``organizer``.

        :param organizer: The organizer to check
        :param perm_name: The permission, e.g. ``can_change_teams``
        :return: bool
        """
        if self.is_superuser:
            return True
        teams = self._get_teams_for_organizer(organizer)
        if teams:
            if not perm_name or any([team.has_permission(perm_name) for team in teams]):
                return True
        return False

    def get_events_with_any_permission(self):
        """
        Returns a queryset of events the user has any permissions to.

        :return: Iterable of Events
        """
        from .event import Event

        if self.is_superuser:
            return Event.objects.all()

        return Event.objects.filter(
            Q(organizer_id__in=self.teams.filter(all_events=True).values_list('organizer', flat=True))
            | Q(id__in=self.teams.values_list('limit_events__id', flat=True))
        )

    def get_events_with_permission(self, permission):
        """
        Returns a queryset of events the user has a specific permissions to.

        :return: Iterable of Events
        """
        from .event import Event

        if self.is_superuser:
            return Event.objects.all()

        kwargs = {permission: True}

        return Event.objects.filter(
            Q(organizer_id__in=self.teams.filter(all_events=True, **kwargs).values_list('organizer', flat=True))
            | Q(id__in=self.teams.filter(**kwargs).values_list('limit_events__id', flat=True))
        )


class U2FDevice(Device):
    json_data = models.TextField()
