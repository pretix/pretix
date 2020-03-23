import string

from django.db import models
from django.db.models import Max
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager, scopes_disabled

from pretix.base.models import LoggedModel


@scopes_disabled()
def generate_serial():
    serial = get_random_string(allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', length=16)
    while Device.objects.filter(unique_serial=serial).exists():
        serial = get_random_string(allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', length=16)
    return serial


@scopes_disabled()
def generate_initialization_token():
    token = get_random_string(length=16, allowed_chars=string.ascii_lowercase + string.digits)
    while Device.objects.filter(initialization_token=token).exists():
        token = get_random_string(length=16, allowed_chars=string.ascii_lowercase + string.digits)
    return token


@scopes_disabled()
def generate_api_token():
    token = get_random_string(length=64, allowed_chars=string.ascii_lowercase + string.digits)
    while Device.objects.filter(api_token=token).exists():
        token = get_random_string(length=64, allowed_chars=string.ascii_lowercase + string.digits)
    return token


class Device(LoggedModel):
    organizer = models.ForeignKey(
        'pretixbase.Organizer',
        on_delete=models.PROTECT,
        related_name='devices'
    )
    device_id = models.PositiveIntegerField()
    unique_serial = models.CharField(max_length=190, default=generate_serial, unique=True)
    initialization_token = models.CharField(max_length=190, default=generate_initialization_token, unique=True)
    api_token = models.CharField(max_length=190, unique=True, null=True)
    all_events = models.BooleanField(default=False, verbose_name=_("All events (including newly created ones)"))
    limit_events = models.ManyToManyField('Event', verbose_name=_("Limit to events"), blank=True)
    revoked = models.BooleanField(default=False)
    name = models.CharField(
        max_length=190,
        verbose_name=_('Name')
    )
    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Setup date')
    )
    initialized = models.DateTimeField(
        verbose_name=_('Initialization date'),
        null=True,
    )
    hardware_brand = models.CharField(
        max_length=190,
        null=True, blank=True
    )
    hardware_model = models.CharField(
        max_length=190,
        null=True, blank=True
    )
    software_brand = models.CharField(
        max_length=190,
        null=True, blank=True
    )
    software_version = models.CharField(
        max_length=190,
        null=True, blank=True
    )

    objects = ScopedManager(organizer='organizer')

    class Meta:
        unique_together = (('organizer', 'device_id'),)

    def __str__(self):
        return '#{}: {} ({} {})'.format(
            self.device_id, self.name, self.hardware_brand, self.hardware_model
        )

    def save(self, *args, **kwargs):
        if not self.device_id:
            self.device_id = (self.organizer.devices.aggregate(m=Max('device_id'))['m'] or 0) + 1
        super().save(*args, **kwargs)

    def permission_set(self) -> set:
        return {
            'can_view_orders',
            'can_change_orders',
            'can_manage_gift_cards'
        }

    def get_event_permission_set(self, organizer, event) -> set:
        """
        Gets a set of permissions (as strings) that a token holds for a particular event

        :param organizer: The organizer of the event
        :param event: The event to check
        :return: set of permissions
        """
        has_event_access = (self.all_events and organizer == self.organizer) or (
            event in self.limit_events.all()
        )
        return self.permission_set() if has_event_access else set()

    def get_organizer_permission_set(self, organizer) -> set:
        """
        Gets a set of permissions (as strings) that a token holds for a particular organizer

        :param organizer: The organizer of the event
        :return: set of permissions
        """
        return self.permission_set() if self.organizer == organizer else set()

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
        has_event_access = (self.all_events and organizer == self.organizer) or (
            event in self.limit_events.all()
        )
        if isinstance(perm_name, (tuple, list)):
            return has_event_access and any(p in self.permission_set() for p in perm_name)
        return has_event_access and (not perm_name or perm_name in self.permission_set())

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
            return organizer == self.organizer and any(p in self.permission_set() for p in perm_name)
        return organizer == self.organizer and (not perm_name or perm_name in self.permission_set())

    def get_events_with_any_permission(self):
        """
        Returns a queryset of events the token has any permissions to.

        :return: Iterable of Events
        """
        if self.all_events:
            return self.organizer.events.all()
        else:
            return self.limit_events.all()
