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
# This file contains Apache-licensed contributions copyrighted by: Christopher Dambamuromo, Sohalt, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import string
from datetime import date, datetime, time

import pytz_deprecation_shim
from django.conf import settings
from django.core.mail import get_connection
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import gettext_lazy as _
from i18nfield.fields import I18nCharField

from pretix.base.models.base import LoggedModel
from pretix.base.validators import OrganizerSlugBanlistValidator

from ..settings import settings_hierarkey
from .auth import User


@settings_hierarkey.add(cache_namespace='organizer')
class Organizer(LoggedModel):
    """
    This model represents an entity organizing events, e.g. a company, institution,
    charity, person, …

    :param name: The organizer's name
    :type name: str
    :param slug: A globally unique, short name for this organizer, to be used
                 in URLs and similar places.
    :type slug: str
    """

    settings_namespace = 'organizer'
    name = models.CharField(max_length=200,
                            verbose_name=_("Name"))
    slug = models.CharField(
        max_length=50, db_index=True,
        help_text=_(
            "Should be short, only contain lowercase letters, numbers, dots, and dashes. Every slug can only be used "
            "once. This is being used in URLs to refer to your organizer accounts and your events."),
        validators=[
            MinLengthValidator(
                limit_value=2,
            ),
            RegexValidator(
                regex="^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$",
                message=_("The slug may only contain letters, numbers, dots and dashes.")
            ),
            OrganizerSlugBanlistValidator()
        ],
        verbose_name=_("Short form"),
        unique=True
    )

    class Meta:
        verbose_name = _("Organizer")
        verbose_name_plural = _("Organizers")
        ordering = ("name", "slug")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        is_new = not self.pk
        obj = super().save(*args, **kwargs)
        if is_new:
            kwargs.pop('update_fields', None)  # does not make sense here
            self.set_defaults()
        else:
            self.get_cache().clear()
        return obj

    def set_defaults(self):
        """
        This will be called after organizer creation.
        This way, we can use this to introduce new default settings to pretix that do not affect existing organizers.
        """
        self.settings.cookie_consent = True

    def get_cache(self):
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this organizer, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the organizer changes.

        .. deprecated:: 1.9
           Use the property ``cache`` instead.
        """
        return self.cache

    @cached_property
    def cache(self):
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this organizer, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the organizer changes.
        """
        from pretix.base.cache import ObjectRelatedCache

        return ObjectRelatedCache(self)

    @property
    def timezone(self):
        return pytz_deprecation_shim.timezone(self.settings.timezone)

    @cached_property
    def all_logentries_link(self):
        return reverse(
            'control:organizer.log',
            kwargs={
                'organizer': self.slug,
            }
        )

    @property
    def has_gift_cards(self):
        return self.cache.get_or_set(
            key='has_gift_cards',
            timeout=15,
            default=lambda: self.issued_gift_cards.exists() or self.gift_card_issuer_acceptance.filter(active=True).exists()
        )

    @property
    def accepted_gift_cards(self):
        from .giftcards import GiftCard, GiftCardAcceptance

        return GiftCard.objects.filter(
            Q(issuer=self) |
            Q(issuer__in=GiftCardAcceptance.objects.filter(
                acceptor=self,
                active=True,
            ).values_list('issuer', flat=True))
        )

    @property
    def default_gift_card_expiry(self):
        if self.settings.giftcard_expiry_years is not None:
            tz = get_current_timezone()
            return make_aware(datetime.combine(
                date(now().astimezone(tz).year + self.settings.get('giftcard_expiry_years', as_type=int), 12, 31),
                time(hour=23, minute=59, second=59)
            ), tz)

    def allow_delete(self):
        from . import Invoice, Order
        return (
            not Order.objects.filter(event__organizer=self).exists() and
            not Invoice.objects.filter(event__organizer=self).exists() and
            not self.devices.exists()
        )

    def delete_sub_objects(self):
        for e in self.events.all():
            e.delete_sub_objects()
            e.delete()
        self.teams.all().delete()

    def get_mail_backend(self, timeout=None):
        """
        Returns an email server connection, either by using the system-wide connection
        or by returning a custom one based on the organizer's settings.
        """
        if self.settings.smtp_use_custom:
            return get_connection(backend=settings.EMAIL_CUSTOM_SMTP_BACKEND,
                                  host=self.settings.smtp_host,
                                  port=self.settings.smtp_port,
                                  username=self.settings.smtp_username,
                                  password=self.settings.smtp_password,
                                  use_tls=self.settings.smtp_use_tls,
                                  use_ssl=self.settings.smtp_use_ssl,
                                  fail_silently=False, timeout=timeout)
        else:
            return get_connection(fail_silently=False)


def generate_invite_token():
    return get_random_string(length=32, allowed_chars=string.ascii_lowercase + string.digits)


def generate_api_token():
    return get_random_string(length=64, allowed_chars=string.ascii_lowercase + string.digits)


class Team(LoggedModel):
    """
    A team is a collection of people given certain access rights to one or more events of an organizer.

    :param name: The name of this team
    :type name: str
    :param organizer: The organizer this team belongs to
    :type organizer: Organizer
    :param members: A set of users who belong to this team
    :param all_events: Whether this team has access to all events of this organizer
    :type all_events: bool
    :param limit_events: A set of events this team has access to. Irrelevant if ``all_events`` is ``True``.
    :param can_create_events: Whether or not the members can create new events with this organizer account.
    :type can_create_events: bool
    :param can_change_teams: If ``True``, the members can change the teams of this organizer account.
    :type can_change_teams: bool
    :param can_manage_customers: If ``True``, the members can view and change organizer-level customer accounts.
    :type can_manage_customers: bool
    :param can_manage_reusable_media: If ``True``, the members can view and change organizer-level reusable media.
    :type can_manage_reusable_media: bool
    :param can_change_organizer_settings: If ``True``, the members can change the settings of this organizer account.
    :type can_change_organizer_settings: bool
    :param can_change_event_settings: If ``True``, the members can change the settings of the associated events.
    :type can_change_event_settings: bool
    :param can_change_items: If ``True``, the members can change and add items and related objects for the associated events.
    :type can_change_items: bool
    :param can_view_orders: If ``True``, the members can inspect details of all orders of the associated events.
    :type can_view_orders: bool
    :param can_change_orders: If ``True``, the members can change details of orders of the associated events.
    :type can_change_orders: bool
    :param can_checkin_orders: If ``True``, the members can perform check-in related actions.
    :type can_checkin_orders: bool
    :param can_view_vouchers: If ``True``, the members can inspect details of all vouchers of the associated events.
    :type can_view_vouchers: bool
    :param can_change_vouchers: If ``True``, the members can change and create vouchers for the associated events.
    :type can_change_vouchers: bool
    """
    organizer = models.ForeignKey(Organizer, related_name="teams", on_delete=models.CASCADE)
    name = models.CharField(max_length=190, verbose_name=_("Team name"))
    members = models.ManyToManyField(User, related_name="teams", verbose_name=_("Team members"))
    all_events = models.BooleanField(default=False, verbose_name=_("All events (including newly created ones)"))
    limit_events = models.ManyToManyField('Event', verbose_name=_("Limit to events"), blank=True)

    can_create_events = models.BooleanField(
        default=False,
        verbose_name=_("Can create events"),
    )
    can_change_teams = models.BooleanField(
        default=False,
        verbose_name=_("Can change teams and permissions"),
    )
    can_change_organizer_settings = models.BooleanField(
        default=False,
        verbose_name=_("Can change organizer settings"),
        help_text=_('Someone with this setting can get access to most data of all of your events, i.e. via privacy '
                    'reports, so be careful who you add to this team!')
    )
    can_manage_customers = models.BooleanField(
        default=False,
        verbose_name=_("Can manage customer accounts")
    )
    can_manage_reusable_media = models.BooleanField(
        default=False,
        verbose_name=_("Can manage reusable media")
    )
    can_manage_gift_cards = models.BooleanField(
        default=False,
        verbose_name=_("Can manage gift cards")
    )
    can_change_event_settings = models.BooleanField(
        default=False,
        verbose_name=_("Can change event settings")
    )
    can_change_items = models.BooleanField(
        default=False,
        verbose_name=_("Can change product settings")
    )
    can_view_orders = models.BooleanField(
        default=False,
        verbose_name=_("Can view orders")
    )
    can_change_orders = models.BooleanField(
        default=False,
        verbose_name=_("Can change orders")
    )
    can_checkin_orders = models.BooleanField(
        default=False,
        verbose_name=_("Can perform check-ins"),
        help_text=_('This includes searching for attendees, which can be used to obtain personal information about '
                    'attendees. Users with "can change orders" can also perform check-ins.')
    )
    can_view_vouchers = models.BooleanField(
        default=False,
        verbose_name=_("Can view vouchers")
    )
    can_change_vouchers = models.BooleanField(
        default=False,
        verbose_name=_("Can change vouchers")
    )

    def __str__(self) -> str:
        return _("%(name)s on %(object)s") % {
            'name': str(self.name),
            'object': str(self.organizer),
        }

    def permission_set(self) -> set:
        attribs = dir(self)
        return {
            a for a in attribs if a.startswith('can_') and self.has_permission(a)
        }

    @property
    def can_change_settings(self):  # Legacy compatiblilty
        return self.can_change_event_settings

    def has_permission(self, perm_name):
        try:
            return getattr(self, perm_name)
        except AttributeError:
            raise ValueError('Invalid required permission: %s' % perm_name)

    def permission_for_event(self, event):
        if self.all_events:
            return event.organizer_id == self.organizer_id
        else:
            return self.limit_events.filter(pk=event.pk).exists()

    @property
    def active_tokens(self):
        return self.tokens.filter(active=True)

    class Meta:
        verbose_name = _("Team")
        verbose_name_plural = _("Teams")


class TeamInvite(models.Model):
    """
    A TeamInvite represents someone who has been invited to a team but hasn't accept the invitation
    yet.

    :param team: The team the person is invited to
    :type team: Team
    :param email: The email the invite has been sent to
    :type email: str
    :param token: The secret required to redeem the invite
    :type token: str
    """
    team = models.ForeignKey(Team, related_name="invites", on_delete=models.CASCADE)
    email = models.EmailField(null=True, blank=True)
    token = models.CharField(default=generate_invite_token, max_length=64, null=True, blank=True)

    def __str__(self) -> str:
        return _("Invite to team '{team}' for '{email}'").format(
            team=str(self.team), email=self.email
        )


class TeamAPIToken(models.Model):
    """
    A TeamAPIToken represents an API token that has the same access level as the team it belongs to.

    :param team: The team the person is invited to
    :type team: Team
    :param name: A human-readable name for the token
    :type name: str
    :param active: Whether or not this token is active
    :type active: bool
    :param token: The secret required to submit to the API
    :type token: str
    """
    team = models.ForeignKey(Team, related_name="tokens", on_delete=models.CASCADE)
    name = models.CharField(max_length=190)
    active = models.BooleanField(default=True)
    token = models.CharField(default=generate_api_token, max_length=64)

    def get_event_permission_set(self, organizer, event) -> set:
        """
        Gets a set of permissions (as strings) that a token holds for a particular event

        :param organizer: The organizer of the event
        :param event: The event to check
        :return: set of permissions
        """
        has_event_access = (self.team.all_events and organizer == self.team.organizer) or (
            event in self.team.limit_events.all()
        )
        return self.team.permission_set() if has_event_access else set()

    def get_organizer_permission_set(self, organizer) -> set:
        """
        Gets a set of permissions (as strings) that a token holds for a particular organizer

        :param organizer: The organizer of the event
        :return: set of permissions
        """
        return self.team.permission_set() if self.team.organizer == organizer else set()

    def has_event_permission(self, organizer, event, perm_name=None, request=None) -> bool:
        """
        Checks if this token is part of a team that grants access of type ``perm_name``
        to the event ``event``.

        :param organizer: The organizer of the event
        :param event: The event to check
        :param perm_name: The permission, e.g. ``can_change_teams``
        :param request: This parameter is ignored and only defined for compatibility reasons.
        :return: bool
        """
        has_event_access = (self.team.all_events and organizer == self.team.organizer) or (
            event in self.team.limit_events.all()
        )
        if isinstance(perm_name, (tuple, list)):
            return has_event_access and any(self.team.has_permission(p) for p in perm_name)
        return has_event_access and (not perm_name or self.team.has_permission(perm_name))

    def has_organizer_permission(self, organizer, perm_name=None, request=None):
        """
        Checks if this token is part of a team that grants access of type ``perm_name``
        to the organizer ``organizer``.

        :param organizer: The organizer to check
        :param perm_name: The permission, e.g. ``can_change_teams``
        :param request: This parameter is ignored and only defined for compatibility reasons.
        :return: bool
        """
        if isinstance(perm_name, (tuple, list)):
            return organizer == self.team.organizer and any(self.team.has_permission(p) for p in perm_name)
        return organizer == self.team.organizer and (not perm_name or self.team.has_permission(perm_name))

    def get_events_with_any_permission(self):
        """
        Returns a queryset of events the token has any permissions to.

        :return: Iterable of Events
        """
        if self.team.all_events:
            return self.team.organizer.events.all()
        else:
            return self.team.limit_events.all()

    def get_events_with_permission(self, permission, request=None):
        """
        Returns a queryset of events the token has a specific permissions to.

        :param request: Ignored, for compatibility with User model
        :return: Iterable of Events
        """
        if (
                isinstance(permission, (list, tuple)) and any(getattr(self.team, p, False) for p in permission)
        ) or (isinstance(permission, str) and getattr(self.team, permission, False)):
            return self.get_events_with_any_permission()
        else:
            return self.team.organizer.events.none()


class OrganizerFooterLink(models.Model):
    """
    A footer link assigned to an organizer.
    """
    organizer = models.ForeignKey('Organizer', on_delete=models.CASCADE, related_name='footer_links')
    label = I18nCharField(
        max_length=200,
        verbose_name=_("Link text"),
    )
    url = models.URLField(
        verbose_name=_("Link URL"),
    )

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.organizer.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.organizer.cache.clear()
