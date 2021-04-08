from django.db import models
from jsonfallback.fields import FallbackJSONField

from django.utils.translation import gettext_lazy as _
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
        help_text=_('If this is not selected, the membership can only be used to purchase tickets with the same '
                    'attendee name as the original membership purchase.'),
        default=False
    )

    def __str__(self):
        return self.name


class Membership(models.Model):
    id = models.BigAutoField(primary_key=True)
    customer = models.ForeignKey(Customer, related_name='memberships', on_delete=models.PROTECT)
    membership_type = models.ForeignKey(MembershipType, related_name='memberships', on_delete=models.PROTECT)
    granted_in = models.ForeignKey('OrderPosition', related_name='granted_memberships', on_delete=models.PROTECT)
    date_from = models.DateTimeField()
    date_end = models.DateTimeField()
    attendee_name_parts = FallbackJSONField(default=dict, null=True)
