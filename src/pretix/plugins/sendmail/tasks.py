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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Sohalt, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
from django.db.models import Exists, OuterRef, Q
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Checkin, Event, InvoiceAddress, Order, User
from pretix.base.services.mail import SendMailException, mail
from pretix.base.services.tasks import ProfiledEventTask
from pretix.celery_app import app
from pretix.helpers.format import format_map


@app.task(base=ProfiledEventTask, acks_late=True)
def send_mails_to_orders(event: Event, user: int, subject: dict, message: dict, objects: list, items: list,
                         recipients: str, filter_checkins: bool, not_checked_in: bool, checkin_lists: list,
                         attachments: list = None, attach_tickets: bool = False,
                         attach_ical: bool = False) -> None:
    failures = []
    user = User.objects.get(pk=user) if user else None
    orders = Order.objects.filter(pk__in=objects, event=event)
    subject = LazyI18nString(subject)
    message = LazyI18nString(message)

    for o in orders:
        send_to_order = recipients in ('both', 'orders')

        try:
            ia = o.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = InvoiceAddress(order=o)

        if recipients in ('both', 'attendees'):
            for p in o.positions.annotate(
                any_checkins=Exists(
                    Checkin.objects.filter(
                        Q(position_id=OuterRef('pk')) | Q(position__addon_to_id=OuterRef('pk')),
                    )
                ),
                matching_checkins=Exists(
                    Checkin.objects.filter(
                        Q(position_id=OuterRef('pk')) | Q(position__addon_to_id=OuterRef('pk')),
                        list_id__in=checkin_lists or []
                    )
                ),
            ).prefetch_related('addons'):
                if p.addon_to_id is not None:
                    continue

                if p.item_id not in items and not any(a.item_id in items for a in p.addons.all()):
                    continue

                if filter_checkins:
                    allowed = (
                        (not_checked_in and not p.any_checkins)
                        or p.matching_checkins
                    )
                    if not allowed:
                        continue

                if not p.attendee_email:
                    if recipients == 'attendees':
                        send_to_order = True
                    continue

                if p.attendee_email == o.email and send_to_order:
                    continue

                try:
                    with language(o.locale, event.settings.region):
                        email_context = get_email_context(event=event, order=o, invoice_address=ia, position=p)
                        mail(
                            p.attendee_email,
                            subject,
                            message,
                            email_context,
                            event,
                            locale=o.locale,
                            order=o,
                            position=p,
                            attach_tickets=attach_tickets,
                            attach_ical=attach_ical,
                            attach_cached_files=attachments
                        )
                        o.log_action(
                            'pretix.plugins.sendmail.order.email.sent.attendee',
                            user=user,
                            data={
                                'position': p.positionid,
                                'subject': format_map(subject.localize(o.locale), email_context),
                                'message': format_map(message.localize(o.locale), email_context),
                                'recipient': p.attendee_email
                            }
                        )
                except SendMailException:
                    failures.append(p.attendee_email)

        if send_to_order and o.email:
            try:
                with language(o.locale, event.settings.region):
                    email_context = get_email_context(event=event, order=o, invoice_address=ia)
                    mail(
                        o.email,
                        subject,
                        message,
                        email_context,
                        event,
                        locale=o.locale,
                        order=o,
                        attach_tickets=attach_tickets,
                        attach_ical=attach_ical,
                        attach_cached_files=attachments,
                    )
                    o.log_action(
                        'pretix.plugins.sendmail.order.email.sent',
                        user=user,
                        data={
                            'subject': format_map(subject.localize(o.locale), email_context),
                            'message': format_map(message.localize(o.locale), email_context),
                            'recipient': o.email
                        }
                    )
            except SendMailException:
                failures.append(o.email)


@app.task(base=ProfiledEventTask, acks_late=True)
def send_mails_to_waitinglist(event: Event, user: int, subject: dict, message: dict, objects: list,
                              attachments: list = None) -> None:
    user = User.objects.get(pk=user) if user else None
    entries = event.waitinglistentries.filter(pk__in=objects).select_related(
        'subevent'
    )
    subject = LazyI18nString(subject)
    message = LazyI18nString(message)

    for e in entries:
        e.send_mail(
            subject,
            message,
            get_email_context(
                event=e.event,
                waiting_list_entry=e,
                event_or_subevent=e.subevent or e.event,
            ),
            user=user,
            attach_cached_files=attachments,
        )
