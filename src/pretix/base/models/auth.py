#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import binascii
import json
import operator
from datetime import timedelta
from functools import reduce
from urllib.parse import urlparse

import webauthn
from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin,
)
from django.contrib.auth.tokens import default_token_generator
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils.crypto import get_random_string, salted_hmac
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_otp.models import Device
from django_scopes import scopes_disabled
from u2flib_server.utils import (
    pub_key_from_der, websafe_decode, websafe_encode,
)

from pretix.base.i18n import language
from pretix.helpers.urls import build_absolute_uri

from .base import LoggingMixin


class EmailAddressTakenError(IntegrityError):
    pass


class UserManager(BaseUserManager):
    """
    This is the user manager for our custom user model. See the User
    model documentation to see what's so special about our user model.
    """

    def create_user(self, email: str, password: str = None, **kwargs):
        user = self.model(email=email, **kwargs)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email: str, password: str = None):  # NOQA
        # Not used in the software but required by Django
        if password is None:
            raise Exception("You must provide a password")
        user = self.model(email=email)
        user.is_staff = True
        user.set_password(password)
        user.save()
        return user

    def get_or_create_for_backend(self, backend, identifier, email, set_always, set_on_creation):
        """
        This method should be used by third-party authentication backends to log in a user.
        It either returns an already existing user or creates a new user.

        In pretix 4.7 and earlier, email addresses were the only property to identify a user with.
        Starting with pretix 4.8, backends SHOULD instead use a unique, immutable identifier
        based on their backend data store to allow for changing email addresses.

        This method transparently handles the conversion of old user accounts and adds the
        backend identifier to their database record.

        This method will never return users managed by a different authentication backend.
        If you try to create an account with an email address already blocked by a different
        authentication backend, :py:class:`EmailAddressTakenError` will be raised. In this case,
        you should display a message to the user.

        :param backend: The `identifier` attribute of the authentication backend
        :param identifier: The unique, immutable identifier of this user, max. 190 characters
        :param email: The user's email address
        :param set_always: A dictionary of fields to update on the user model on every login
        :param set_on_creation: A dictionary of fields to set on the user model if it's newly created
        :return: A `User` instance.
        """
        if identifier is None:
            raise ValueError('You need to supply a custom, unique identifier for this user.')
        if email is None:
            raise ValueError('You need to supply an email address for this user.')
        if 'auth_backend_identifier' in set_always or 'auth_backend_identifier' in set_on_creation or \
                'auth_backend' in set_always or 'auth_backend' in set_on_creation:
            raise ValueError('You may not update auth_backend/auth_backend_identifier.')
        if len(identifier) > 190:
            raise ValueError('The user identifier must not be more than 190 characters.')

        # Always update the email address
        set_always.update({'email': email})

        # First, check if we find the user based on it's backend-specific authenticator
        try:
            u = self.get(
                auth_backend=backend,
                auth_backend_identifier=identifier,
            )
            dirty = False
            for k, v in set_always.items():
                if getattr(u, k) != v:
                    setattr(u, k, v)
                    dirty = True
            if dirty:
                try:
                    with transaction.atomic():
                        u.save(update_fields=set_always.keys())
                except IntegrityError:
                    # This might only raise IntegrityError if the email address is used
                    # by someone else
                    raise EmailAddressTakenError()
            return u
        except self.model.DoesNotExist:
            pass

        # Second, check if we find the user based on their email address and this backend
        try:
            u = self.get(
                auth_backend=backend,
                auth_backend_identifier__isnull=True,
                email=email,
            )
            u.auth_backend_identifier = identifier
            for k, v in set_always.items():
                setattr(u, k, v)
            try:
                with transaction.atomic():
                    u.save(update_fields=['auth_backend_identifier'] + list(set_always.keys()))
                return u
            except IntegrityError:
                # This might only raise IntegrityError if this code is being executed twice
                # and runs into a race condition, this mechanism is taken from Django's
                # get_or_create
                try:
                    return self.get(
                        auth_backend=backend,
                        auth_backend_identifier=identifier,
                    )
                except self.model.DoesNotExist:
                    pass
                raise
        except self.model.DoesNotExist:
            pass

        # Third, create a new user
        u = User(
            auth_backend=backend,
            auth_backend_identifier=identifier,
            **set_on_creation,
            **set_always,
        )
        try:
            u.save(force_insert=True)
            return u
        except IntegrityError:
            # This might either be a race condition or the email address is taken
            # by a different backend
            try:
                return self.get(
                    auth_backend=backend,
                    auth_backend_identifier=identifier,
                )
            except self.model.DoesNotExist:
                raise EmailAddressTakenError()


def generate_notifications_token():
    return get_random_string(length=32)


def generate_session_token():
    return get_random_string(length=32)


class SuperuserPermissionSet:
    def __contains__(self, item):
        return True


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
    :param needs_password_change: Whether this user's password needs to be changed.
    :type needs_password_change: bool
    :param timezone: The user's preferred timezone.
    :type timezone: str
    :param auth_backend: The identifier of the authentication backend plugin responsible for managing this user.
    :type auth_backend: str
    :param auth_backend_identifier: The native identifier of the user provided by a non-native authentication backend.
    :type auth_backend_identifier: str
    """

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    email = models.EmailField(unique=True, db_index=True, null=True, blank=True,
                              verbose_name=_('E-mail'), max_length=190)
    fullname = models.CharField(max_length=255, blank=True, null=True,
                                verbose_name=_('Full name'))
    is_active = models.BooleanField(default=True,
                                    verbose_name=_('Is active'))
    is_staff = models.BooleanField(default=False,
                                   verbose_name=_('Is site admin'))
    date_joined = models.DateTimeField(auto_now_add=True,
                                       verbose_name=_('Date joined'))
    needs_password_change = models.BooleanField(default=False,
                                                verbose_name=_('Force user to select a new password'))
    locale = models.CharField(max_length=50,
                              choices=settings.LANGUAGES,
                              default=settings.LANGUAGE_CODE,
                              verbose_name=_('Language'))
    timezone = models.CharField(max_length=100,
                                default=settings.TIME_ZONE,
                                verbose_name=_('Timezone'))
    require_2fa = models.BooleanField(
        default=False,
        verbose_name=_('Two-factor authentication is required to log in')
    )
    notifications_send = models.BooleanField(
        default=True,
        verbose_name=_('Receive notifications according to my settings below'),
        help_text=_('If turned off, you will not get any notifications.')
    )
    notifications_token = models.CharField(max_length=255, default=generate_notifications_token)
    auth_backend = models.CharField(max_length=255, default='native')
    auth_backend_identifier = models.CharField(max_length=190, db_index=True, null=True, blank=True)
    session_token = models.CharField(max_length=32, default=generate_session_token)

    objects = UserManager()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._teamcache = {}

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ('email',)
        unique_together = (('auth_backend', 'auth_backend_identifier'),)

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        is_new = not self.pk
        super().save(*args, **kwargs)
        if is_new:
            self.notification_settings.create(
                action_type='pretix.event.order.refund.requested',
                event=None,
                method='mail',
                enabled=True
            )

    def __str__(self):
        return self.email

    @property
    def is_superuser(self):
        return False

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
        from pretix.base.services.mail import SendMailException, mail

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
                user=self,
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
            None, locale=self.locale, user=self
        )

    @property
    def top_logentries(self):
        return self.all_logentries

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

    def get_event_permission_set(self, organizer, event) -> set:
        """
        Gets a set of permissions (as strings) that a user holds for a particular event

        :param organizer: The organizer of the event
        :param event: The event to check
        :return: set
        """
        teams = self._get_teams_for_event(organizer, event)
        sets = [t.permission_set() for t in teams]
        if sets:
            return set.union(*sets)
        else:
            return set()

    def get_organizer_permission_set(self, organizer) -> set:
        """
        Gets a set of permissions (as strings) that a user holds for a particular organizer

        :param organizer: The organizer of the event
        :return: set
        """
        teams = self._get_teams_for_organizer(organizer)
        sets = [t.permission_set() for t in teams]
        if sets:
            return set.union(*sets)
        else:
            return set()

    def has_event_permission(self, organizer, event, perm_name=None, request=None) -> bool:
        """
        Checks if this user is part of any team that grants access of type ``perm_name``
        to the event ``event``.

        :param organizer: The organizer of the event
        :param event: The event to check
        :param perm_name: The permission, e.g. ``can_change_teams``
        :param request: The current request (optional). Required to detect staff sessions properly.
        :return: bool
        """
        if request and self.has_active_staff_session(request.session.session_key):
            return True
        teams = self._get_teams_for_event(organizer, event)
        if teams:
            self._teamcache['e{}'.format(event.pk)] = teams
            if isinstance(perm_name, (tuple, list)):
                return any([any(team.has_permission(p) for team in teams) for p in perm_name])
            if not perm_name or any([team.has_permission(perm_name) for team in teams]):
                return True
        return False

    def has_organizer_permission(self, organizer, perm_name=None, request=None):
        """
        Checks if this user is part of any team that grants access of type ``perm_name``
        to the organizer ``organizer``.

        :param organizer: The organizer to check
        :param perm_name: The permission, e.g. ``can_change_teams``
        :param request: The current request (optional). Required to detect staff sessions properly.
        :return: bool
        """
        if request and self.has_active_staff_session(request.session.session_key):
            return True
        teams = self._get_teams_for_organizer(organizer)
        if teams:
            if isinstance(perm_name, (tuple, list)):
                return any([any(team.has_permission(p) for team in teams) for p in perm_name])
            if not perm_name or any([team.has_permission(perm_name) for team in teams]):
                return True
        return False

    @scopes_disabled()
    def get_events_with_any_permission(self, request=None):
        """
        Returns a queryset of events the user has any permissions to.

        :param request: The current request (optional). Required to detect staff sessions properly.
        :return: Iterable of Events
        """
        from .event import Event

        if request and self.has_active_staff_session(request.session.session_key):
            return Event.objects.all()

        return Event.objects.filter(
            Q(organizer_id__in=self.teams.filter(all_events=True).values_list('organizer', flat=True))
            | Q(id__in=self.teams.values_list('limit_events__id', flat=True))
        )

    @scopes_disabled()
    def get_events_with_permission(self, permission, request=None):
        """
        Returns a queryset of events the user has a specific permissions to.

        :param request: The current request (optional). Required to detect staff sessions properly.
        :return: Iterable of Events
        """
        from .event import Event

        if request and self.has_active_staff_session(request.session.session_key):
            return Event.objects.all()

        if isinstance(permission, (tuple, list)):
            q = reduce(operator.or_, [Q(**{p: True}) for p in permission])
        else:
            q = Q(**{permission: True})

        return Event.objects.filter(
            Q(organizer_id__in=self.teams.filter(q, all_events=True).values_list('organizer', flat=True))
            | Q(id__in=self.teams.filter(q).values_list('limit_events__id', flat=True))
        )

    @scopes_disabled()
    def get_organizers_with_any_permission(self, request=None):
        """
        Returns a queryset of organizers the user has any permissions to.

        :param request: The current request (optional). Required to detect staff sessions properly.
        :return: Iterable of Organizers
        """
        from .event import Organizer

        if request and self.has_active_staff_session(request.session.session_key):
            return Organizer.objects.all()

        return Organizer.objects.filter(
            id__in=self.teams.values_list('organizer', flat=True)
        )

    @scopes_disabled()
    def get_organizers_with_permission(self, permission, request=None):
        """
        Returns a queryset of organizers the user has a specific permissions to.

        :param request: The current request (optional). Required to detect staff sessions properly.
        :return: Iterable of Organizers
        """
        from .event import Organizer

        if request and self.has_active_staff_session(request.session.session_key):
            return Organizer.objects.all()

        kwargs = {permission: True}

        return Organizer.objects.filter(
            id__in=self.teams.filter(**kwargs).values_list('organizer', flat=True)
        )

    def has_active_staff_session(self, session_key=None):
        """
        Returns whether or not a user has an active staff session (formerly known as superuser session)
        with the given session key.
        """
        return self.get_active_staff_session(session_key) is not None

    def get_active_staff_session(self, session_key=None):
        if not self.is_staff:
            return None
        if not hasattr(self, '_staff_session_cache'):
            self._staff_session_cache = {}
        if session_key not in self._staff_session_cache:
            qs = StaffSession.objects.filter(
                user=self, date_end__isnull=True
            )
            if session_key:
                qs = qs.filter(session_key=session_key)
            sess = qs.first()
            if sess:
                if sess.date_start < now() - timedelta(seconds=settings.PRETIX_SESSION_TIMEOUT_ABSOLUTE):
                    sess.date_end = now()
                    sess.save()
                    sess = None

            self._staff_session_cache[session_key] = sess
        return self._staff_session_cache[session_key]

    def get_session_auth_hash(self):
        """
        Return an HMAC that needs to
        """
        key_salt = "pretix.base.models.User.get_session_auth_hash"
        payload = self.password
        payload += self.email
        payload += self.session_token
        return salted_hmac(key_salt, payload).hexdigest()

    def update_session_token(self):
        self.session_token = generate_session_token()
        self.save(update_fields=['session_token'])


class StaffSession(models.Model):
    user = models.ForeignKey('User', on_delete=models.PROTECT)
    date_start = models.DateTimeField(auto_now_add=True)
    date_end = models.DateTimeField(null=True, blank=True)
    session_key = models.CharField(max_length=255)
    comment = models.TextField()

    class Meta:
        ordering = ('date_start',)


class StaffSessionAuditLog(models.Model):
    session = models.ForeignKey('StaffSession', related_name='logs', on_delete=models.PROTECT)
    datetime = models.DateTimeField(auto_now_add=True)
    url = models.CharField(max_length=255)
    method = models.CharField(max_length=255)
    impersonating = models.ForeignKey('User', null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ('datetime',)


class U2FDevice(Device):
    json_data = models.TextField()

    @property
    def webauthnuser(self):
        d = json.loads(self.json_data)
        # We manually need to convert the pubkey from DER format (used in our
        # former U2F implementation) to the format required by webauthn. This
        # is based on the following example:
        # https://www.w3.org/TR/webauthn/#sctn-encoded-credPubKey-examples
        pub_key = pub_key_from_der(websafe_decode(d['publicKey'].replace('+', '-').replace('/', '_')))
        pub_key = binascii.unhexlify(
            'A5010203262001215820{:064x}225820{:064x}'.format(
                pub_key.public_numbers().x, pub_key.public_numbers().y
            )
        )
        return webauthn.WebAuthnUser(
            d['keyHandle'],
            self.user.email,
            str(self.user),
            settings.SITE_URL,
            d['keyHandle'],
            websafe_encode(pub_key),
            1,
            urlparse(settings.SITE_URL).netloc
        )


class WebAuthnDevice(Device):
    credential_id = models.CharField(max_length=255, null=True, blank=True)
    rp_id = models.CharField(max_length=255, null=True, blank=True)
    icon_url = models.CharField(max_length=255, null=True, blank=True)
    ukey = models.TextField(null=True)
    pub_key = models.TextField(null=True)
    sign_count = models.IntegerField(default=0)

    @property
    def webauthnuser(self):
        return webauthn.WebAuthnUser(
            self.ukey,
            self.user.email,
            str(self.user),
            settings.SITE_URL,
            self.credential_id,
            self.pub_key,
            self.sign_count,
            urlparse(settings.SITE_URL).netloc
        )
