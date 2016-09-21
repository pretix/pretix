from typing import Any, Dict

from django.conf import settings
from django.core.files.base import ContentFile

from pretix.base.models import CachedFile, Event, cachedfile_name
from pretix.base.signals import register_data_exporters
from pretix.celery import app


@app.task()
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
