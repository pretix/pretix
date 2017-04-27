import string

from django.core.validators import RegexValidator
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from pretix.base.models.base import LoggedModel
from pretix.base.validators import OrganizerSlugBlacklistValidator

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
    slug = models.SlugField(
        max_length=50, db_index=True,
        help_text=_(
            "Should be short, only contain lowercase letters and numbers, and must be unique among your events. "
            "This is being used in addresses and bank transfer references."),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9.-]+$",
                message=_("The slug may only contain letters, numbers, dots and dashes.")
            ),
            OrganizerSlugBlacklistValidator()
        ],
        verbose_name=_("Short form"),
    )
    permitted = models.ManyToManyField(User, through='OrganizerPermission',
                                       related_name="organizers")

    class Meta:
        verbose_name = _("Organizer")
        verbose_name_plural = _("Organizers")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)
        self.get_cache().clear()
        return obj

    def get_cache(self) -> "pretix.base.cache.ObjectRelatedCache":
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this organizer, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the organizer changes.
        """
        from pretix.base.cache import ObjectRelatedCache

        return ObjectRelatedCache(self)


def generate_invite_token():
    return get_random_string(length=32, allowed_chars=string.ascii_lowercase + string.digits)


class OrganizerPermission(models.Model):
    """
    The relation between an Organizer and a User who has permissions to
    access an organizer profile.

    :param organizer: The organizer this relation refers to
    :type organizer: Organizer
    :param user: The user this set of permissions is valid for
    :type user: User
    :param can_create_events: Whether or not this user can create new events with this
                              organizer account.
    :type can_create_events: bool
    """

    organizer = models.ForeignKey(Organizer, related_name="user_perms", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="organizer_perms", on_delete=models.CASCADE, null=True, blank=True)
    invite_email = models.EmailField(null=True, blank=True)
    invite_token = models.CharField(default=generate_invite_token, max_length=64, null=True, blank=True)
    can_create_events = models.BooleanField(
        default=True,
        verbose_name=_("Can create events"),
    )
    can_change_permissions = models.BooleanField(
        default=True,
        verbose_name=_("Can change permissions"),
    )

    class Meta:
        verbose_name = _("Organizer permission")
        verbose_name_plural = _("Organizer permissions")

    def __str__(self) -> str:
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.organizer),
        }


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
        verbose_name=_("Can change organizer settings")
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

    @property
    def can_change_settings(self):  # Legacy compatiblilty
        return self.can_change_event_settings

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
