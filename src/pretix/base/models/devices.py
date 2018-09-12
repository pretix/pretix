import string

from django.db import models
from django.db.models import Max
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _


def generate_serial():
    serial = get_random_string(allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', length=16)
    while Device.objects.filter(unique_serial=serial).exists():
        serial = get_random_string(allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', length=16)
    return serial


def generate_initialization_token():
    token = get_random_string(length=16, allowed_chars=string.ascii_lowercase + string.digits)
    while Device.objects.filter(initialization_token=token).exists():
        token = get_random_string(length=16, allowed_chars=string.ascii_lowercase + string.digits)
    return token


def generate_api_token():
    token = get_random_string(length=64, allowed_chars=string.ascii_lowercase + string.digits)
    while Device.objects.filter(initialization_token=token).exists():
        token = get_random_string(length=64, allowed_chars=string.ascii_lowercase + string.digits)
    return token


class Device(models.Model):
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

    class Meta:
        unique_together = (('organizer', 'device_id'),)

    def __str__(self):
        return '#{} ({} {})'.format(
            self.device_id, self.hardware_brand, self.hardware_model
        )

    def save(self, *args, **kwargs):
        if not self.device_id:
            self.device_id = (self.organizer.devices.aggregate(m=Max('device_id'))['m'] or 0) + 1
        super().save(*args, **kwargs)
