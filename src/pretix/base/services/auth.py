from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Q
from django.dispatch import receiver
from django.utils.timezone import now

from pretix.base.models.auth import StaffSession

from ..signals import periodic_task


@receiver(signal=periodic_task)
def close_inactive_staff_sessions(sender, **kwargs):
    StaffSession.objects.annotate(last_used=Max('logs__datetime')).filter(
        Q(last_used__lte=now() - timedelta(seconds=settings.PRETIX_SESSION_TIMEOUT_RELATIVE)) & Q(date_end__isnull=True)
    ).update(
        date_end=now()
    )
