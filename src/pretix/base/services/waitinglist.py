from django.dispatch import receiver

from pretix.base.models import Event, User, WaitingListEntry
from pretix.base.models.waitinglist import WaitingListException
from pretix.base.services.async import ProfiledTask
from pretix.base.signals import periodic_task
from pretix.celery_app import app


@app.task(base=ProfiledTask)
def assign_automatically(event_id: int, user_id: int=None):
    event = Event.objects.get(id=event_id)
    if user_id:
        user = User.objects.get(id=user_id)
    else:
        user = None

    quota_cache = {}
    gone = set()

    qs = WaitingListEntry.objects.filter(
        event=event, voucher__isnull=True
    ).select_related('item', 'variation').prefetch_related('item__quotas', 'variation__quotas').order_by('created')
    sent = 0

    for wle in qs:
        if (wle.item, wle.variation) in gone:
            continue

        quotas = wle.variation.quotas.all() if wle.variation else wle.item.quotas.all()
        availability = (
            wle.variation.check_quotas(count_waitinglist=False, _cache=quota_cache)
            if wle.variation
            else wle.item.check_quotas(count_waitinglist=False, _cache=quota_cache)
        )
        if availability[1] > 0:
            try:
                wle.send_voucher(quota_cache, user=user)
                sent += 1
            except WaitingListException:  # noqa
                continue

            # Reduce affected quotas in cache
            for q in quotas:
                quota_cache[q.pk] = (
                    quota_cache[q.pk][0] if quota_cache[q.pk][0] > 1 else 0,
                    quota_cache[q.pk][1] - 1
                )
        else:
            gone.add((wle.item, wle.variation))

    return sent


@receiver(signal=periodic_task)
def process_waitinglist(sender, **kwargs):
    qs = Event.objects.prefetch_related('setting_objects', 'organizer__setting_objects').select_related('organizer')
    for e in qs:
        if e.settings.waiting_list_enabled and e.settings.waiting_list_auto:
            assign_automatically.apply_async(args=(e.pk,))
