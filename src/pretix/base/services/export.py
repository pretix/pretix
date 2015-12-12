from django.conf import settings
from django.core.files.base import ContentFile
from typing import Any, Dict

from pretix.base.models import CachedFile, Event, cachedfile_name
from pretix.base.signals import register_data_exporters


def export(event: str, fileid: str, provider: str, form_data: Dict[str, Any]) -> None:
    event = Event.objects.get(id=event)
    file = CachedFile.objects.get(id=fileid)
    responses = register_data_exporters.send(event)
    for receiver, response in responses:
        ex = response(event)
        if ex.identifier == provider:
            file.filename, file.type, data = ex.render(form_data)
            file.file.save(cachedfile_name(file, file.filename), ContentFile(data))
            file.save()


if settings.HAS_CELERY:
    from pretix.celery import app

    export_task = app.task(export)
    export = lambda *args, **kwargs: export_task.apply_async(args=args, kwargs=kwargs)
