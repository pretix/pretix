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
import logging
from datetime import timedelta
from typing import Any, Dict

from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.core.files.base import ContentFile
from django.dispatch import receiver
from django.utils.timezone import now, override
from django.utils.translation import gettext
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.exporter import OrganizerLevelExportMixin
from pretix.base.i18n import LazyLocaleException, language
from pretix.base.models import (
    CachedFile, Device, Event, Organizer, ScheduledEventExport, TeamAPIToken,
    User, cachedfile_name,
)
from pretix.base.services.mail import mail
from pretix.base.services.tasks import (
    ProfiledEventTask, ProfiledOrganizerUserTask,
)
from pretix.base.signals import (
    periodic_task, register_data_exporters, register_multievent_data_exporters,
)
from pretix.celery_app import app
from pretix.helpers.urls import build_absolute_uri

logger = logging.getLogger(__name__)


class ExportError(LazyLocaleException):
    pass


class ExportEmptyError(ExportError):
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
        for recv, response in responses:
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

        for recv, response in responses:
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


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=120)
def scheduled_export(self, event: Event, schedule: int) -> None:
    schedule = event.scheduled_exports.get(pk=schedule)

    with language(schedule.locale, event.settings.region), override(event.settings.timezone):
        file = CachedFile(web_download=False)
        file.date = now()
        file.expires = now() + timedelta(hours=24)
        file.save()

        def _handle_error(msg, soft=False):
            event.log_action(
                'pretix.event.export.schedule.failed',
                user=self.request.user, data={
                    'id': schedule.id,
                    'export_identifier': schedule.export_identifier,
                    'export_form_data': schedule.export_form_data,
                    'reason': msg,
                    'soft': soft,
                }
            )
            mail(
                email=schedule.owner.email,
                subject=gettext('Export failed'),
                template='pretixbase/email/export_failed.txt',
                context={
                    'configuration_url': build_absolute_uri(
                        'control:event.orders.export',
                        kwargs={
                            'event': event.slug,
                            'organizer': event.organizer.slug,
                        }
                    ) + f'?identifier={schedule.export_identifier}&scheduled={schedule.pk}',
                    'reason': msg,
                    'soft': soft,
                },
                event=event,
                locale=schedule.locale,
            )
            if not soft:
                schedule.error_counter += 1
                schedule.error_last_message = msg
                schedule.save(update_fields=['error_counter', 'error_last_message'])

        if not schedule.owner.has_event_permission(event.organizer, event, 'can_view_orders'):
            _handle_error(gettext('Permission denied.'))

        try:
            responses = register_data_exporters.send(event)
            for recv, response in responses:
                if not response:
                    continue
                ex = response(event, event.organizer)
                if ex.identifier == schedule.export_identifier:
                    d = ex.render(schedule.export_form_data)
                    if d is None:
                        raise ExportEmptyError(
                            gettext('Your export did not contain any data.')
                        )
                    file.filename, file.type, data = d
                    filesize = len(data)
                    if filesize > 20 * 1024 * 1024:  # 20 MB
                        raise ExportError(
                            gettext('Your exported data exceeded the size limit for scheduled exports.')
                        )
                    f = ContentFile(data)
                    file.file.save(cachedfile_name(file, file.filename), f)
                    break
            else:
                raise ExportError("Export type not found.")
        except ExportEmptyError as e:
            _handle_error(e, soft=True)
        except ExportError as e:
            _handle_error(e, soft=False)
        except Exception:
            logger.exception("Scheduled export failed.")
            try:
                self.retry()
            except MaxRetriesExceededError:
                _handle_error('Internal Error')
        else:
            mail(
                email=[schedule.owner.email] + [r for r in schedule.mail_additional_recipients.split(",") if r],
                cc=[r for r in schedule.mail_additional_recipients_cc.split(",") if r],
                bcc=[r for r in schedule.mail_additional_recipients_bcc.split(",") if r],
                subject=schedule.mail_subject,
                template=LazyI18nString(schedule.mail_template),
                context=get_email_context(event=event),
                event=event,
                locale=schedule.locale,
                attach_cached_files=[file],
            )
            event.log_action(
                'pretix.event.export.schedule.executed',
                data={
                    'id': schedule.id,
                    'export_identifier': schedule.export_identifier,
                    'export_form_data': schedule.export_form_data,
                    'result_file_size': filesize,
                    'result_file_name': file.file.name,
                }
            )


@receiver(signal=periodic_task)
@scopes_disabled()
def run_scheduled_exports(sender, **kwargs):
    qs = ScheduledEventExport.objects.filter(
        schedule_next_run__lt=now(),
    ).select_related('event')
    for s in qs:
        scheduled_export.apply_async(kwargs={
            'event': s.event.pk,
            'schedule': s.pk,
        })
        s.compute_next_run()
        s.save(update_fields=['schedule_next_run'])
