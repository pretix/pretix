from typing import Any, Dict

from django.core.files.base import ContentFile
from django.utils.timezone import override
from django.utils.translation import gettext

from pretix.base.i18n import LazyLocaleException, language
from pretix.base.models import (
    CachedFile, Event, Organizer, User, cachedfile_name,
)
from pretix.base.services.tasks import (
    ProfiledEventTask, ProfiledOrganizerUserTask,
)
from pretix.base.signals import (
    register_data_exporters, register_multievent_data_exporters,
)
from pretix.celery_app import app


class ExportError(LazyLocaleException):
    pass


@app.task(base=ProfiledEventTask, throws=(ExportError,))
def export(event: Event, fileid: str, provider: str, form_data: Dict[str, Any]) -> None:
    file = CachedFile.objects.get(id=fileid)
    with language(event.settings.locale), override(event.settings.timezone):
        responses = register_data_exporters.send(event)
        for receiver, response in responses:
            ex = response(event)
            if ex.identifier == provider:
                d = ex.render(form_data)
                if d is None:
                    raise ExportError(
                        gettext('Your export did not contain any data.')
                    )
                file.filename, file.type, data = d
                file.file.save(cachedfile_name(file, file.filename), ContentFile(data))
                file.save()
    return file.pk


@app.task(base=ProfiledOrganizerUserTask, throws=(ExportError,))
def multiexport(organizer: Organizer, user: User, fileid: str, provider: str, form_data: Dict[str, Any]) -> None:
    file = CachedFile.objects.get(id=fileid)
    with language(user.locale), override(user.timezone):
        allowed_events = user.get_events_with_permission('can_view_orders')

        events = allowed_events.filter(pk__in=form_data.get('events'))
        responses = register_multievent_data_exporters.send(organizer)

        for receiver, response in responses:
            if not response:
                continue
            ex = response(events)
            if ex.identifier == provider:
                d = ex.render(form_data)
                if d is None:
                    raise ExportError(
                        gettext('Your export did not contain any data.')
                    )
                file.filename, file.type, data = d
                file.file.save(cachedfile_name(file, file.filename), ContentFile(data))
                file.save()
    return file.pk
