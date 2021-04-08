from django.db import models
from django.utils.translation import gettext_lazy as _
from jsonfallback.fields import FallbackJSONField

from pretix.base.models import Customer
from pretix.base.models.base import LoggedModel
from pretix.base.models.organizer import Organizer


class MembershipType(LoggedModel):
    id = models.BigAutoField(primary_key=True)
    organizer = models.ForeignKey(Organizer, related_name='membership_types', on_delete=models.CASCADE)
    name = models.CharField(
        verbose_name=_('Name'),
        max_length=255
    )
    transferable = models.BooleanField(
        verbose_name=_('Membership is transferable'),
        help_text=_('If this is selected, the membership can be used to purchase tickets for multiple persons. If not, '
                    'the attendee name always needs to stay the same.'),
        default=False
    )

    def __str__(self):
        return self.name

    def allow_delete(self):
        return not self.memberships.exists() and not self.granted_by.exists()


class Membership(models.Model):
    id = models.BigAutoField(primary_key=True)
    customer = models.ForeignKey(
        Customer,
        related_name='memberships',
        on_delete=models.PROTECT
    )
    membership_type = models.ForeignKey(
        MembershipType,
        verbose_name=_('Membership type'),
        related_name='memberships',
        on_delete=models.PROTECT
    )
    granted_in = models.ForeignKey(
        'OrderPosition',
        related_name='granted_memberships',
        on_delete=models.PROTECT
    )
    date_from = models.DateTimeField(
        verbose_name=_('Start date')
    )
    date_end = models.DateTimeField(
        verbose_name=_('End date')
    )
    attendee_name_parts = FallbackJSONField(default=dict, null=True)
