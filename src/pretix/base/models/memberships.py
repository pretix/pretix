from django.db import models
from django.utils.translation import gettext_lazy as _
from i18nfield.fields import I18nCharField
from jsonfallback.fields import FallbackJSONField

from pretix.base.models import Customer
from pretix.base.models.base import LoggedModel
from pretix.base.models.organizer import Organizer
from pretix.base.settings import PERSON_NAME_SCHEMES


class MembershipType(LoggedModel):
    id = models.BigAutoField(primary_key=True)
    organizer = models.ForeignKey(Organizer, related_name='membership_types', on_delete=models.CASCADE)
    name = I18nCharField(
        verbose_name=_('Name'),
    )
    transferable = models.BooleanField(
        verbose_name=_('Membership is transferable'),
        help_text=_('If this is selected, the membership can be used to purchase tickets for multiple persons. If not, '
                    'the attendee name always needs to stay the same.'),
        default=False
    )
    allow_parallel_usage = models.BooleanField(
        verbose_name=_('Parallel usage is allowed'),
        help_text=_('If this is selected, the membership can be used to purchase tickets for events happening at the same time.'),
        default=False
    )
    max_usages = models.PositiveIntegerField(
        verbose_name=_("Maximum usages"),
        help_text=_("Number of times this membership can be used in a purchase."),
        null=True, blank=True,
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
    date_start = models.DateTimeField(
        verbose_name=_('Start date')
    )
    date_end = models.DateTimeField(
        verbose_name=_('End date')
    )
    attendee_name_parts = FallbackJSONField(default=dict, null=True)

    @property
    def attendee_name(self):
        if not self.attendee_name_parts:
            return None
        if '_legacy' in self.attendee_name_parts:
            return self.attendee_name_parts['_legacy']
        if '_scheme' in self.attendee_name_parts:
            scheme = PERSON_NAME_SCHEMES[self.attendee_name_parts['_scheme']]
        else:
            scheme = PERSON_NAME_SCHEMES[self.customer.organizer.settings.name_scheme]
        return scheme['concatenation'](self.attendee_name_parts).strip()

    class Meta:
        ordering = "-date_end", "-date_start", "membership_type"
