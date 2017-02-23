import string

from django.core.validators import RegexValidator
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from pretix.base.models.base import LoggedModel
from pretix.base.settings import SettingsProxy
from pretix.base.validators import OrganizerSlugBlacklistValidator

from .auth import User
from .settings import OrganizerSetting


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

    @cached_property
    def settings(self) -> SettingsProxy:
        """
        Returns an object representing this organizer's settings
        """
        from pretix.base.settings import GlobalSettingsObject
        return SettingsProxy(self, type=OrganizerSetting, parent=GlobalSettingsObject())

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
