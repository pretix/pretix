import sys

from django.dispatch import receiver
from django_scopes import scopes_disabled

from pretix.base.models import Event, User, WaitingListEntry
from pretix.base.models.waitinglist import WaitingListException
from pretix.base.services.tasks import EventTask
from pretix.base.signals import periodic_task
from pretix.celery_app import app


@app.task(base=EventTask)
def assign_automatically(event: Event, user_id: int=None, subevent_id: int=None):
    if user_id:
        user = User.objects.get(id=user_id)
    else:
        user = None

    quota_cache = {}
    gone = set()

    qs = WaitingListEntry.objects.filter(
        event=event, voucher__isnull=True
    ).select_related('item', 'variation').prefetch_related(
        'item__quotas', 'variation__quotas'
    ).order_by('-priority', 'created')

    if subevent_id and event.has_subevents:
        subevent = event.subevents.get(id=subevent_id)
        qs = qs.filter(subevent=subevent)

    sent = 0

    with event.lock():
        for wle in qs:
            if (wle.item, wle.variation) in gone:
                continue

            ev = (wle.subevent or event)
            if not ev.presale_is_running or (wle.subevent and not wle.subevent.active):
                continue

            quotas = (wle.variation.quotas.filter(subevent=wle.subevent)
                      if wle.variation
                      else wle.item.quotas.filter(subevent=wle.subevent))
            availability = (
                wle.variation.check_quotas(count_waitinglist=False, _cache=quota_cache, subevent=wle.subevent)
                if wle.variation
                else wle.item.check_quotas(count_waitinglist=False, _cache=quota_cache, subevent=wle.subevent)
            )
            if availability[1] is None or availability[1] > 0:
                try:
                    wle.send_voucher(quota_cache, user=user)
                    sent += 1
                except WaitingListException:  # noqa
                    continue

                # Reduce affected quotas in cache
                for q in quotas:
                    quota_cache[q.pk] = (
                        quota_cache[q.pk][0] if quota_cache[q.pk][0] > 1 else 0,
                        quota_cache[q.pk][1] - 1 if quota_cache[q.pk][1] is not None else sys.maxsize
                    )
            else:
                gone.add((wle.item, wle.variation))

    return sent


@receiver(signal=periodic_task)
@scopes_disabled()
def process_waitinglist(sender, **kwargs):
    qs = Event.objects.filter(
        live=True
    ).prefetch_related('_settings_objects', 'organizer___settings_objects').select_related('organizer')
    for e in qs:
        if e.settings.waiting_list_auto and e.presale_is_running:
            assign_automatically.apply_async(args=(e.pk,))
