from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.timezone import now

from pretix.base.models import CachedFile, CachedTicket, Order, cachedfile_name
from pretix.base.signals import register_ticket_outputs


def generate(order: str, provider: str):
    order = Order.objects.select_related('event').get(id=order)
    ct = CachedTicket.objects.get_or_create(order=order, provider=provider)[0]
    if not ct.cachedfile:
        cf = CachedFile()
        cf.date = now()
        cf.expires = order.event.date_from + timedelta(days=30)
        cf.save()
        ct.cachedfile = cf
        ct.save()

    responses = register_ticket_outputs.send(order.event)
    for receiver, response in responses:
        prov = response(order.event)
        if prov.identifier == provider:
            ct.cachedfile.filename, ct.cachedfile.type, data = prov.generate(order)
            ct.cachedfile.file.save(cachedfile_name(ct.cachedfile, ct.cachedfile.filename), ContentFile(data))
            ct.cachedfile.save()


if settings.HAS_CELERY:
    from pretix.celery import app

    generate_task = app.task(generate)
    generate = lambda *args, **kwargs: generate_task.apply_async(args=args, kwargs=kwargs)
