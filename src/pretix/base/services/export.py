from typing import Any, Dict

from django.core.files.base import ContentFile
from django.utils.timezone import override
from django.utils.translation import ugettext

from pretix.base.i18n import LazyLocaleException, language
from pretix.base.models import CachedFile, Event, cachedfile_name
from pretix.base.services.tasks import ProfiledTask
from pretix.base.signals import register_data_exporters
from pretix.celery_app import app


class ExportError(LazyLocaleException):
    pass


@app.task(base=ProfiledTask, throws=(ExportError,))
def export(event: str, fileid: str, provider: str, form_data: Dict[str, Any]) -> None:
    event = Event.objects.get(id=event)
    file = CachedFile.objects.get(id=fileid)
    with language(event.settings.locale), override(event.settings.timezone):
        responses = register_data_exporters.send(event)
        for receiver, response in responses:
            ex = response(event)
            if ex.identifier == provider:
                d = ex.render(form_data)
                if d is None:
                    raise ExportError(
                        ugettext('Your export did not contain any data.')
                    )
                file.filename, file.type, data = d
                file.file.save(cachedfile_name(file, file.filename), ContentFile(data))
                file.save()
    return file.pk
