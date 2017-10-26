from django.db import models
from django.db.models import F, Max, OuterRef, Q, Subquery
from django.dispatch import receiver

from pretix.base.models import LogEntry, Quota
from pretix.celery_app import app

from ..signals import periodic_task


@receiver(signal=periodic_task)
def build_all_quota_caches(sender, **kwargs):
    refresh_quota_caches.apply_async()


@app.task
def refresh_quota_caches():
    last_activity = LogEntry.objects.filter(
        event=OuterRef('event_id'),
    ).order_by().values('event').annotate(
        m=Max('datetime')
    ).values(
        'm'
    )
    quotas = Quota.objects.annotate(
        last_activity=Subquery(last_activity, output_field=models.DateTimeField())
    ).filter(
        Q(cached_availability_time__isnull=True) |
        Q(cached_availability_time__lt=F('last_activity'))
    )
    for q in quotas:
        q.availability()
