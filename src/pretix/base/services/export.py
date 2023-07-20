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
from typing import Any, Dict, Union

from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import close_old_connections, connection, transaction
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
from pretix.base.models.exports import ScheduledOrganizerExport
from pretix.base.services.mail import mail
from pretix.base.services.tasks import (
    EventTask, OrganizerTask, ProfiledEventTask, ProfiledOrganizerUserTask,
)
from pretix.base.signals import (
    periodic_task, register_data_exporters, register_multievent_data_exporters,
)
from pretix.celery_app import app
from pretix.helpers import OF_SELF
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

                close_old_connections()  # This task can run very long, we might need a new DB connection

                f = ContentFile(data)
                file.file.save(cachedfile_name(file, file.filename), f)
    return str(file.pk)


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
        if form_data.get('events') is not None and not form_data.get('all_events'):
            if isinstance(form_data['events'][0], str):
                events = allowed_events.filter(slug__in=form_data.get('events'), organizer=organizer)
            else:
                events = allowed_events.filter(pk__in=form_data.get('events'), organizer=organizer)
        else:
            events = allowed_events.filter(organizer=organizer)
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

                close_old_connections()  # This task can run very long, we might need a new DB connection

                f = ContentFile(data)
                file.file.save(cachedfile_name(file, file.filename), f)
    return str(file.pk)


def _run_scheduled_export(schedule, context: Union[Event, Organizer], exporter, config_url, retry_func, has_permission):
    with language(schedule.locale, context.settings.region), override(schedule.tz):
        file = CachedFile(web_download=False)
        file.date = now()
        file.expires = now() + timedelta(hours=24)
        file.save()

        def _handle_error(msg, soft=False):
            context.log_action(
                'pretix.event.export.schedule.failed',
                data={
                    'id': schedule.id,
                    'export_identifier': schedule.export_identifier,
                    'export_form_data': schedule.export_form_data,
                    'reason': msg,
                    'soft': soft,
                }
            )
            if schedule.owner.is_active:
                mail(
                    email=schedule.owner.email,
                    subject=gettext('Export failed'),
                    template='pretixbase/email/export_failed.txt',
                    context={
                        'configuration_url': config_url,
                        'reason': msg,
                        'soft': soft,
                    },
                    event=context if isinstance(context, Event) else None,
                    organizer=context.organizer if isinstance(context, Event) else context,
                    locale=schedule.locale,
                )
            if not soft:
                schedule.error_counter += 1
                schedule.error_last_message = msg
                schedule.save(update_fields=['error_counter', 'error_last_message'])

        if not has_permission:
            _handle_error(gettext('Permission denied.'))
            return

        try:
            if not exporter:
                raise ExportError("Export type not found.")
            d = exporter.render(schedule.export_form_data)
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

            conn = transaction.get_connection()
            if not conn.in_atomic_block:  # atomic execution only happens during tests or with celery always_eager on
                close_old_connections()  # This task can run very long, we might need a new DB connection

            f = ContentFile(data)
            file.file.save(cachedfile_name(file, file.filename), f)
        except ExportEmptyError as e:
            _handle_error(str(e), soft=True)
        except ExportError as e:
            _handle_error(str(e), soft=False)
        except Exception:
            logger.exception("Scheduled export failed.")
            try:
                retry_func()
            except MaxRetriesExceededError:
                _handle_error('Internal Error')
        else:
            schedule.error_counter = 0
            schedule.save(update_fields=['error_counter'])
            to = [r for r in schedule.mail_additional_recipients.split(",") if r]
            cc = [r for r in schedule.mail_additional_recipients_cc.split(",") if r]
            bcc = [r for r in schedule.mail_additional_recipients_bcc.split(",") if r]
            if to:
                # If there is an explicit To, the owner is Cc. Otherwise, the owner is To. Yes, this is
                # purely cosmetical and has policital reasons.
                cc.append(schedule.owner.email)
            else:
                to.append(schedule.owner.email)

            mail(
                email=to,
                cc=cc,
                bcc=bcc,
                subject=schedule.mail_subject,
                template=LazyI18nString(schedule.mail_template),
                context=get_email_context(event=context) if isinstance(context, Event) else {},
                event=context if isinstance(context, Event) else None,
                organizer=context.organizer if isinstance(context, Event) else context,
                locale=schedule.locale,
                attach_cached_files=[file],
            )
            context.log_action(
                'pretix.event.export.schedule.executed',
                data={
                    'id': schedule.id,
                    'export_identifier': schedule.export_identifier,
                    'export_form_data': schedule.export_form_data,
                    'result_file_size': filesize,
                    'result_file_name': file.file.name,
                }
            )


@app.task(base=OrganizerTask, bind=True, max_retries=5, default_retry_delay=120)
def scheduled_organizer_export(self, organizer: Organizer, schedule: int) -> None:
    schedule = organizer.scheduled_exports.get(pk=schedule)

    allowed_events = schedule.owner.get_events_with_permission('can_view_orders')
    if schedule.export_form_data.get('events') is not None and not schedule.export_form_data.get('all_events'):
        if isinstance(schedule.export_form_data['events'][0], str):
            events = allowed_events.filter(slug__in=schedule.export_form_data.get('events'), organizer=organizer)
        else:
            events = allowed_events.filter(pk__in=schedule.export_form_data.get('events'), organizer=organizer)
    else:
        events = allowed_events.filter(organizer=organizer)

    responses = register_multievent_data_exporters.send(organizer)
    exporter = None
    for recv, response in responses:
        if not response:
            continue
        ex = response(events, organizer)
        if ex.identifier == schedule.export_identifier:
            exporter = ex
            break

    has_permission = schedule.owner.is_active
    if isinstance(exporter, OrganizerLevelExportMixin):
        if not schedule.owner.has_organizer_permission(organizer, exporter.organizer_required_permission):
            has_permission = False
    if exporter and not exporter.available_for_user(schedule.owner):
        has_permission = False

    _run_scheduled_export(
        schedule,
        organizer,
        exporter,
        build_absolute_uri(
            'control:organizer.export',
            kwargs={
                'organizer': organizer.slug,
            }
        ) + f'?identifier={schedule.export_identifier}&scheduled={schedule.pk}',
        self.retry,
        has_permission,
    )


@app.task(base=EventTask, bind=True, max_retries=5, default_retry_delay=120)
def scheduled_event_export(self, event: Event, schedule: int) -> None:
    schedule = event.scheduled_exports.get(pk=schedule)

    responses = register_data_exporters.send(event)
    exporter = None
    for recv, response in responses:
        if not response:
            continue
        ex = response(event, event.organizer)
        if ex.identifier == schedule.export_identifier:
            exporter = ex
            break

    has_permission = schedule.owner.is_active and schedule.owner.has_event_permission(event.organizer, event, 'can_view_orders')

    _run_scheduled_export(
        schedule,
        event,
        exporter,
        build_absolute_uri(
            'control:event.orders.export',
            kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            }
        ) + f'?identifier={schedule.export_identifier}&scheduled={schedule.pk}',
        self.retry,
        has_permission,
    )


@receiver(signal=periodic_task)
@scopes_disabled()
@transaction.atomic
def run_scheduled_exports(sender, **kwargs):
    qs = ScheduledEventExport.objects.filter(
        schedule_next_run__lt=now(),
        error_counter__lt=5,
    ).select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked, of=OF_SELF).select_related('event')
    for s in qs:
        scheduled_event_export.apply_async(kwargs={
            'event': s.event_id,
            'schedule': s.pk,
        })
        s.compute_next_run()
        s.save(update_fields=['schedule_next_run'])
    qs = ScheduledOrganizerExport.objects.filter(
        schedule_next_run__lt=now(),
        error_counter__lt=5,
    ).select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked, of=OF_SELF).select_related('organizer')
    for s in qs:
        scheduled_organizer_export.apply_async(kwargs={
            'organizer': s.organizer_id,
            'schedule': s.pk,
        })
        s.compute_next_run()
        s.save(update_fields=['schedule_next_run'])
