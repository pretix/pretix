from django.core.validators import RegexValidator
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from pretix.base.models.base import LoggedModel
from pretix.base.settings import SettingsProxy

from .auth import User


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
            )
        ],
        verbose_name=_("Slug"),
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
        return SettingsProxy(self, type=OrganizerSetting)

    def get_cache(self) -> "pretix.base.cache.ObjectRelatedCache":
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this organizer, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the organizer changes.
        """
        from pretix.base.cache import ObjectRelatedCache

        return ObjectRelatedCache(self)


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
    user = models.ForeignKey(User, related_name="organizer_perms")
    can_create_events = models.BooleanField(
        default=True,
        verbose_name=_("Can create events"),
    )

    class Meta:
        verbose_name = _("Organizer permission")
        verbose_name_plural = _("Organizer permissions")

    def __str__(self) -> str:
        return _("%(name)s on %(object)s") % {
            'name': str(self.user),
            'object': str(self.organizer),
        }


class OrganizerSetting(models.Model):
    """
    An event option is a key-value setting which can be set for an
    organizer. It will be inherited by the events of this organizer
    """
    object = models.ForeignKey(Organizer, related_name='setting_objects', on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    value = models.TextField()
