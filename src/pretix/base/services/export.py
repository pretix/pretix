#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from typing import Any, Dict

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.timezone import override
from django.utils.translation import gettext

from pretix.base.exporter import OrganizerLevelExportMixin
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
            if not response:
                continue
            ex = response(event, event.organizer, set_progress)
            if ex.identifier == provider:
                d = ex.render(form_data)
                if d is None:
                    raise ExportError(
                        gettext('Your export did not contain any data.')
                    )
                file.filename, file.type, data = d
                f = ContentFile(data)
                file.file.save(cachedfile_name(file, file.filename), f)
    return file.pk


@app.task(base=ProfiledOrganizerUserTask, throws=(ExportError,), bind=True)
def multiexport(self, organizer: Organizer, user: User, device: int, token: int, fileid: str, provider: str,
                form_data: Dict[str, Any], staff_session=False) -> None:
    if device:
        device = Device.objects.get(pk=device)
    if token:
        device = TeamAPIToken.objects.get(pk=token)
    allowed_events = (device or token or user).get_events_with_permission('can_view_orders')
    if user and staff_session:
        allowed_events = organizer.events.all()

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
            locale = organizer.settings.locale or settings.LANGUAGE_CODE
            timezone = organizer.settings.timezone or settings.TIME_ZONE
            region = organizer.settings.region
    with language(locale, region), override(timezone):
        if form_data.get('events') is not None:
            if isinstance(form_data['events'][0], str):
                events = allowed_events.filter(slug__in=form_data.get('events'), organizer=organizer)
            else:
                events = allowed_events.filter(pk__in=form_data.get('events'))
        else:
            events = allowed_events
        responses = register_multievent_data_exporters.send(organizer)

        for receiver, response in responses:
            if not response:
                continue
            ex = response(events, organizer, set_progress)
            if ex.identifier == provider:
                if (
                    isinstance(ex, OrganizerLevelExportMixin) and
                    not staff_session and
                    not (device or token or user).has_organizer_permission(organizer, ex.organizer_required_permission)
                ):
                    raise ExportError(
                        gettext('You do not have sufficient permission to perform this export.')
                    )

                d = ex.render(form_data)
                if d is None:
                    raise ExportError(
                        gettext('Your export did not contain any data.')
                    )
                file.filename, file.type, data = d
                f = ContentFile(data)
                file.file.save(cachedfile_name(file, file.filename), f)
    return file.pk
