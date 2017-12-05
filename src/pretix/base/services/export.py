from typing import Any, Dict

from django.core.files.base import ContentFile
from django.utils.timezone import override

from pretix.base.i18n import language
from pretix.base.models import CachedFile, Event, cachedfile_name
from pretix.base.services.async import ProfiledTask
from pretix.base.signals import register_data_exporters
from pretix.celery_app import app


@app.task(base=ProfiledTask)
def export(event: str, fileid: str, provider: str, form_data: Dict[str, Any]) -> None:
    event = Event.objects.get(id=event)
    file = CachedFile.objects.get(id=fileid)
    with language(event.settings.locale), override(event.settings.timezone):
        responses = register_data_exporters.send(event)
        for receiver, response in responses:
            ex = response(event)
            if ex.identifier == provider:
                file.filename, file.type, data = ex.render(form_data)
                file.file.save(cachedfile_name(file, file.filename), ContentFile(data))
                file.save()
    return file.pk
