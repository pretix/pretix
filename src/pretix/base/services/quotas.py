from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Q
from django.dispatch import receiver
from django.utils.timezone import now

from pretix.base.models import Event, LogEntry
from pretix.celery_app import app

from ..signals import periodic_task


@receiver(signal=periodic_task)
def build_all_quota_caches(sender, **kwargs):
    refresh_quota_caches.apply_async()


@app.task
def refresh_quota_caches():
    # Active events
    active = LogEntry.objects.using(settings.DATABASE_REPLICA).filter(
        datetime__gt=now() - timedelta(days=7)
    ).order_by().values('event').annotate(
        last_activity=Max('datetime')
    )
    for a in active:
        try:
            e = Event.objects.using(settings.DATABASE_REPLICA).get(pk=a['event'])
        except Event.DoesNotExist:
            continue
        quotas = e.quotas.filter(
            Q(cached_availability_time__isnull=True) |
            Q(cached_availability_time__lt=a['last_activity']) |
            Q(cached_availability_time__lt=now() - timedelta(hours=2))
        ).filter(
            Q(subevent__isnull=True) |
            Q(subevent__date_to__isnull=False, subevent__date_to__gte=now() - timedelta(days=14)) |
            Q(subevent__date_from__gte=now() - timedelta(days=14))
        )
        for q in quotas:
            q.availability()
