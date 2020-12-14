from typing import Any, Dict

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.timezone import override
from django.utils.translation import gettext

from pretix.base.i18n import LazyLocaleException, language
from pretix.base.models import (
    CachedFile, Device, Event, Organizer, TeamAPIToken, User, cachedfile_name,
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


@app.task(base=ProfiledEventTask, throws=(ExportError,), bind=True)
def export(self, event: Event, fileid: str, provider: str, form_data: Dict[str, Any]) -> None:
    def set_progress(val):
        if not self.request.called_directly:
            self.update_state(
                state='PROGRESS',
                meta={'value': val}
            )

    file = CachedFile.objects.get(id=fileid)
    with language(event.settings.locale, event.settings.region), override(event.settings.timezone):
        responses = register_data_exporters.send(event)
        for receiver, response in responses:
            ex = response(event, set_progress)
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


@app.task(base=ProfiledOrganizerUserTask, throws=(ExportError,), bind=True)
def multiexport(self, organizer: Organizer, user: User, device: int, token: int, fileid: str, provider: str, form_data: Dict[str, Any]) -> None:
    if device:
        device = Device.objects.get(pk=device)
    if token:
        device = TeamAPIToken.objects.get(pk=token)
    allowed_events = (device or token or user).get_events_with_permission('can_view_orders')

    def set_progress(val):
        if not self.request.called_directly:
            self.update_state(
                state='PROGRESS',
                meta={'value': val}
            )

    file = CachedFile.objects.get(id=fileid)
    if user:
        locale = user.locale
        timezone = user.timezone
        region = None  # todo: add to user?
    else:
        e = allowed_events.first()
        if e:
            locale = e.settings.locale
            timezone = e.settings.timezone
            region = e.settings.region
        else:
            locale = settings.LANGUAGE_CODE
            timezone = settings.TIME_ZONE
            region = None
    with language(locale, region), override(timezone):
        if isinstance(form_data['events'][0], str):
            events = allowed_events.filter(slug__in=form_data.get('events'), organizer=organizer)
        else:
            events = allowed_events.filter(pk__in=form_data.get('events'))
        responses = register_multievent_data_exporters.send(organizer)

        for receiver, response in responses:
            if not response:
                continue
            ex = response(events, set_progress)
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
