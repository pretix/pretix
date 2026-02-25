#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from pretix.base.exporter import BaseExporter, OrganizerLevelExportMixin
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
from pretix.helpers import OF_SELF, repeatable_reads_transaction
from pretix.helpers.urls import build_absolute_uri

logger = logging.getLogger(__name__)


class ExportError(LazyLocaleException):
    pass


class ExportEmptyError(ExportError):
    pass


@app.task(base=ProfiledEventTask, throws=(ExportError, ExportEmptyError), bind=True)
def export(self, event: Event, user: User, device: int, token: int, fileid: str, provider: str,
           form_data: Dict[str, Any], staff_session=False) -> None:
    if user:
        user = User.objects.get(pk=user)
    if device:
        device = Device.objects.get(pk=device)
    if token:
        device = TeamAPIToken.objects.get(pk=token)

    def set_progress(val):
        if not self.request.called_directly:
            self.update_state(
                state='PROGRESS',
                meta={'value': val}
            )

    ex = init_event_exporter(
        identifier=provider,
        event=event,
        user=user,
        token=token,
        device=device,
        staff_session=staff_session,
        progress_callback=set_progress,
    )
    if not ex:
        raise ExportError(
            gettext('Export not found or you do not have sufficient permission to perform this export.')
        )

    file = CachedFile.objects.get(id=fileid)
    with language(event.settings.locale, event.settings.region), override(event.settings.timezone):
        if ex.repeatable_read:
            with repeatable_reads_transaction():
                d = ex.render(form_data)
        else:
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


@app.task(base=ProfiledOrganizerUserTask, throws=(ExportError, ExportEmptyError), bind=True)
def multiexport(self, organizer: Organizer, user: User, device: int, token: int, fileid: str, provider: str,
                form_data: Dict[str, Any], staff_session=False) -> None:
    if device:
        device = Device.objects.get(pk=device)
    if token:
        token = TeamAPIToken.objects.get(pk=token)

    def set_progress(val):
        if not self.request.called_directly:
            self.update_state(
                state='PROGRESS',
                meta={'value': val}
            )

    file = CachedFile.objects.get(id=fileid)

    event_qs = organizer.events.all()
    if form_data.get('events') is not None and not form_data.get('all_events'):
        if form_data['events'] and isinstance(form_data['events'][0], str):  # legacy API-created schedules
            event_qs = event_qs.filter(slug__in=form_data.get('events'))
        else:
            event_qs = event_qs.filter(pk__in=form_data.get('events'))

    ex = init_organizer_exporter(
        identifier=provider,
        organizer=organizer,
        user=user,
        token=token,
        device=device,
        staff_session=staff_session,
        progress_callback=set_progress,
        event_qs=event_qs,
    )
    if not ex:
        raise ExportError(
            gettext('Export not found or you do not have sufficient permission to perform this export.')
        )

    if user:
        locale = user.locale
        timezone = user.timezone
        region = None  # todo: add to user?
    else:
        e = ex.events.first()
        if e:
            locale = e.settings.locale
            timezone = e.settings.timezone
            region = e.settings.region
        else:
            locale = organizer.settings.locale or settings.LANGUAGE_CODE
            timezone = organizer.settings.timezone or settings.TIME_ZONE
            region = organizer.settings.region
    with language(locale, region), override(timezone):
        if ex.repeatable_read:
            with repeatable_reads_transaction():
                d = ex.render(form_data)
        else:
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


def init_event_exporter(identifier, **kwargs):
    for ex in init_event_exporters(**kwargs):
        if ex.identifier == identifier:
            return ex
    return None


def init_event_exporters(event, user=None, token=None, device=None, request=None, staff_session=False, **kwargs):
    if not user and not token and not device:
        raise ValueError("No auth source given.")
    perm_holder = device or token or user

    responses = register_data_exporters.send(event)
    for r, response in responses:
        if not response:
            continue

        if issubclass(response, OrganizerLevelExportMixin):
            raise TypeError("Cannot user organizer-level exporter on event level")

        permission_name = response.get_required_event_permission()
        if not perm_holder.has_event_permission(event.organizer, event, permission_name, request) and not staff_session:
            continue

        exporter: BaseExporter = response(event=event, organizer=event.organizer, **kwargs)

        if not exporter.available_for_user(user if user and user.is_authenticated else None):
            continue

        yield exporter


def init_organizer_exporter(identifier, **kwargs):
    for ex in init_organizer_exporters(**kwargs):
        if ex.identifier == identifier:
            return ex
    return None


def init_organizer_exporters(
    organizer, user=None, token=None, device=None, request=None, staff_session=False, event_qs=None, **kwargs
):
    if not user and not token and not device:
        raise ValueError("No auth source given.")
    perm_holder = device or token or user

    _event_list_cache = {}
    _has_permission_on_any_team_cache = {}
    _team_cache = None

    responses = register_multievent_data_exporters.send(organizer)
    for r, response in responses:
        if not response:
            continue

        if issubclass(response, OrganizerLevelExportMixin):
            exporter: BaseExporter = response(event=Event.objects.none(), organizer=organizer, **kwargs)

            try:
                if not perm_holder.has_organizer_permission(organizer, response.get_required_organizer_permission(), request) and not staff_session:
                    continue
            except NotImplementedError:
                logger.error(f"Not showing export {response} because get_required_organizer_permission() is not implemented.")
                continue

        else:
            permission_name = response.get_required_event_permission()

            if permission_name not in _event_list_cache:
                if staff_session:
                    events = event_qs.all()
                elif event_qs is not None:
                    events = event_qs.filter(
                        pk__in=perm_holder.get_events_with_permission(
                            permission_name, request=request
                        ).filter(
                            organizer=organizer
                        ).values("id")
                    )
                else:
                    events = perm_holder.get_events_with_permission(
                        permission_name, request=request
                    ).filter(
                        organizer=organizer
                    )

                _event_list_cache[permission_name] = events

            if permission_name not in _has_permission_on_any_team_cache:
                # Check if the user has this event permission on any teams they are part of to decide whether to show
                # the export at all.
                # This is different from _event_list_cache[permission_name].exists() for the case of an organizer with
                # zero events in total, or a team with zero events. In these cases, we still want people to be able
                # to see waht exports they'll get once they have events.
                if user:
                    if _team_cache is None:
                        _team_cache = list(user.teams.filter(organizer=organizer))
                    _has_permission_on_any_team_cache[permission_name] = staff_session or any(
                        t.has_event_permission(permission_name) for t in _team_cache
                    )
                elif token:
                    _has_permission_on_any_team_cache[permission_name] = token.team.has_event_permission(permission_name)
                elif device:
                    _has_permission_on_any_team_cache[permission_name] = device.has_event_permission(permission_name)

            if not _has_permission_on_any_team_cache[permission_name]:
                continue

            exporter: BaseExporter = response(event=_event_list_cache[permission_name], organizer=organizer, **kwargs)

        if not exporter.available_for_user(user if user and user.is_authenticated else None):
            continue

        yield exporter


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
                raise ExportError("Export type not found or permission denied.")
            if exporter.repeatable_read:
                with repeatable_reads_transaction():
                    d = exporter.render(schedule.export_form_data)
            else:
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

    event_qs = organizer.events.all()
    if schedule.export_form_data.get('events') is not None and not schedule.export_form_data.get('all_events'):
        if isinstance(schedule.export_form_data['events'][0], str):
            event_qs = event_qs.filter(slug__in=schedule.export_form_data.get('events'))
        else:
            event_qs = event_qs.filter(pk__in=schedule.export_form_data.get('events'))

    exporter = init_organizer_exporter(
        identifier=schedule.export_identifier,
        organizer=organizer,
        user=schedule.owner,
        event_qs=event_qs,
    )
    has_permission = schedule.owner.is_active

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

    exporter = init_event_exporter(
        identifier=schedule.export_identifier,
        event=event,
        user=schedule.owner,
    )
    has_permission = schedule.owner.is_active

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
