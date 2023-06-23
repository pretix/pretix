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
# This file contains Apache-licensed contributions copyrighted by: Maico Timmerman, Sohalt
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
import json
import os
import time
from typing import List, Tuple

from django.db.models import Max, Q
from django.db.models.functions import Greatest
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretix.api.serializers.order import (
    AnswerSerializer, InvoiceAddressSerializer,
)
from pretix.api.serializers.waitinglist import WaitingListSerializer
from pretix.base.i18n import LazyLocaleException
from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, InvoiceAddress, OrderPayment,
    OrderPosition, OrderRefund, QuestionAnswer,
)
from pretix.base.services.invoices import invoice_pdf_task
from pretix.base.signals import register_data_shredders
from pretix.helpers.json import CustomJSONEncoder


class ShredError(LazyLocaleException):
    pass


def shred_constraints(event: Event):
    if event.has_subevents:
        max_date = event.subevents.aggregate(
            max_from=Max('date_from'),
            max_to=Max('date_to'),
            max_fromto=Greatest(Max('date_to'), Max('date_from'))
        )
        max_date = max_date['max_fromto'] or max_date['max_to'] or max_date['max_from']
        if max_date is not None and max_date >= now():
            return _('Your event needs to be over to use this feature.')
    else:
        if (event.date_to or event.date_from) >= now():
            return _('Your event needs to be over to use this feature.')
    if event.live:
        return _('Your ticket shop needs to be offline to use this feature.')
    return None


class BaseDataShredder:
    """
    This is the base class for all data shredders.
    """

    def __init__(self, event: Event):
        self.event = event

    def __str__(self):
        return self.identifier

    def generate_files(self) -> List[Tuple[str, str, str]]:
        """
        This method is called to export the data that is about to be shred and return a list of tuples consisting of a
        filename, a file type and file content.

        You can also implement this as a generator and ``yield`` those tuples instead of returning a list of them.
        """
        raise NotImplementedError()  # NOQA

    def shred_data(self, progress_callback=None):
        """
        This method is called to actually remove the data from the system. You should remove any database objects
        here.

        You can call ``progress_callback`` with an integer value between 0 and 100 to communicate back your progress.

        You should never delete ``LogEntry`` objects, but you might modify them to remove personal data. In this
        case, set the ``LogEntry.shredded`` attribute to ``True`` to show that this is no longer original log data.
        """
        raise NotImplementedError()  # NOQA

    @property
    def tax_relevant(self):
        """
        Indicates whether this removes potentially tax-relevant data.
        """
        return False

    @property
    def require_download_confirmation(self):
        """
        Indicates whether the data of this shredder needs to be downloaded, before it is actually shredded. By default
        this value is equal to the tax relevant flag.
        """
        return self.tax_relevant

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for what this shredder removes. This should be short but self-explanatory.
        Good examples include 'E-Mail addresses' or 'Invoices'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this shredder.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def description(self) -> str:
        """
        A more detailed description of what this shredder does. Can contain HTML.
        """
        raise NotImplementedError()  # NOQA


def shred_log_fields(logentry, banlist=None, whitelist=None):
    d = logentry.parsed_data
    initial_data = copy.copy(d)
    shredded = False
    if whitelist:
        for k, v in d.items():
            if k not in whitelist:
                d[k] = '█'
                shredded = True
    elif banlist:
        for f in banlist:
            if f in d:
                d[f] = '█'
                shredded = True
    if d != initial_data:
        logentry.data = json.dumps(d)
        logentry.shredded = logentry.shredded or shredded
        logentry.save(update_fields=['data', 'shredded'])


def slow_update(qs, batch_size=1000, sleep_time=.5, progress_callback=None, progress_offset=0, progress_total=None, **update):
    """
    Doing UPDATE queries on hundreds of thousands of rows can cause outages due to high write load on the database.
    This provides a throttled way to update rows. The condition for this to work properly is that the queryset has a
    filter condition that no longer applies after the update!
    Otherwise, this will be an endless loop!
    """
    total_updated = 0
    while True:
        updated = qs.order_by().filter(
            pk__in=qs.order_by().values_list('pk', flat=True)[:batch_size]
        ).update(**update)
        total_updated += updated
        if not updated:
            break
        if total_updated >= 0.8 * batch_size:
            time.sleep(sleep_time)
        if progress_callback and progress_total:
            progress_callback((progress_offset + total_updated) / progress_total)

    return total_updated


def slow_delete(qs, batch_size=1000, sleep_time=.5, progress_callback=None, progress_offset=0, progress_total=None):
    """
    Doing DELETE queries on hundreds of thousands of rows can cause outages due to high write load on the database.
    This provides a throttled way to update rows.
    """
    total_deleted = 0
    while True:
        deleted = qs.order_by().filter(
            pk__in=qs.order_by().values_list('pk', flat=True)[:batch_size]
        ).delete()[0]
        total_deleted += deleted
        if not deleted:
            break
        if total_deleted >= 0.8 * batch_size:
            time.sleep(sleep_time)
    return total_deleted


def _progress_helper(queryset, progress_callback, offset, total):
    if not progress_callback:
        yield from queryset
    else:
        for i, o in enumerate(queryset):
            yield o
            if i % 10 == 0:
                progress_callback((i + offset) / total * 100)


class PhoneNumberShredder(BaseDataShredder):
    verbose_name = _('Phone numbers')
    identifier = 'phone_numbers'
    description = _('This will remove all phone numbers from orders.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'phone-by-order.json', 'application/json', json.dumps({
            o.code: o.phone for o in self.event.orders.filter(phone__isnull=False)
        }, cls=CustomJSONEncoder, indent=4)

    def shred_data(self, progress_callback=None):
        qs_orders = self.event.orders.all()
        qs_orders_cnt = qs_orders.count()
        qs_le = self.event.logentry_set.filter(action_type="pretix.event.order.phone.changed")
        qs_le_cnt = qs_le.count()
        total = qs_le_cnt + qs_orders_cnt

        for o in _progress_helper(qs_orders, progress_callback, 0, total):
            changed = bool(o.phone)
            o.phone = None
            d = o.meta_info_data
            if d:
                if 'contact_form_data' in d and 'phone' in d['contact_form_data']:
                    changed = True
                    del d['contact_form_data']['phone']
                    o.meta_info = json.dumps(d)
            if changed:
                o.save(update_fields=['meta_info', 'phone'])

        for le in _progress_helper(qs_le, progress_callback, qs_orders_cnt, total):
            shred_log_fields(le, banlist=['old_phone', 'new_phone'])


class EmailAddressShredder(BaseDataShredder):
    verbose_name = _('E-mails')
    identifier = 'order_emails'
    description = _('This will remove all e-mail addresses from orders and attendees, as well as logged email '
                    'contents. This will also remove the association to customer accounts.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'emails-by-order.json', 'application/json', json.dumps({
            o.code: o.email for o in self.event.orders.filter(email__isnull=False)
        }, indent=4)
        yield 'emails-by-attendee.json', 'application/json', json.dumps({
            '{}-{}'.format(op.order.code, op.positionid): op.attendee_email
            for op in OrderPosition.all.filter(order__event=self.event, attendee_email__isnull=False)
        }, indent=4)

    def shred_data(self, progress_callback=None):
        qs_op = OrderPosition.all.filter(order__event=self.event, attendee_email__isnull=False)
        qs_op_cnt = qs_op.count()

        qs_orders = self.event.orders.all()
        qs_orders_cnt = qs_orders.count()

        qs_le = self.event.logentry_set.filter(
            Q(action_type__contains="order.email") | Q(action_type__contains="position.email") |
            Q(action_type="pretix.event.order.contact.changed") |
            Q(action_type="pretix.event.order.modified")
        ).exclude(data="")
        qs_le_cnt = qs_le.count()

        total = qs_op_cnt + qs_orders_cnt + qs_le_cnt

        slow_update(
            qs_op,
            attendee_email=None,
            progress_callback=progress_callback,
            progress_offset=0,
            progress_total=total,
            # Updates to order position table are slow, since PostgreSQL needs to update many indexes, so let's
            # take them really slowly to not overwhelm the database.
            batch_size=100,
            sleep_time=2,
        )

        for o in _progress_helper(qs_orders, progress_callback, qs_op_cnt, total):
            changed = bool(o.email) or bool(o.customer)
            o.email = None
            o.customer = None
            d = o.meta_info_data
            if d:
                if 'contact_form_data' in d and 'email' in d['contact_form_data']:
                    del d['contact_form_data']['email']
                    changed = True
                    o.meta_info = json.dumps(d)
                if 'contact_form_data' in d and 'email_repeat' in d['contact_form_data']:
                    del d['contact_form_data']['email_repeat']
                    changed = True
            if changed:
                if d:
                    o.meta_info = json.dumps(d)
                o.save(update_fields=['meta_info', 'email', 'customer'])

        for le in _progress_helper(qs_le, progress_callback, qs_op_cnt + qs_orders_cnt, total):
            if le.action_type == "pretix.event.order.modified":
                d = le.parsed_data
                if 'data' in d:
                    for row in d['data']:
                        if 'attendee_email' in row:
                            row['attendee_email'] = '█'
                    le.data = json.dumps(d)
                    le.shredded = True
                    le.save(update_fields=['data', 'shredded'])
            else:
                shred_log_fields(le, banlist=[
                    'recipient', 'message', 'subject', 'full_mail', 'old_email', 'new_email'
                ])


class WaitingListShredder(BaseDataShredder):
    verbose_name = _('Waiting list')
    identifier = 'waiting_list'
    description = _('This will remove all names, email addresses, and phone numbers from the waiting list.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'waiting-list.json', 'application/json', json.dumps([
            WaitingListSerializer(wle).data
            for wle in self.event.waitinglistentries.all()
        ], indent=4)

    def shred_data(self, progress_callback=None):
        qs_wle = self.event.waitinglistentries.exclude(email='█')
        qs_wle_cnt = qs_wle.count()

        qs_voucher = self.event.waitinglistentries.select_related('voucher').filter(voucher__isnull=False)
        qs_voucher_cnt = qs_voucher.count()

        qs_le = self.event.logentry_set.filter(action_type="pretix.voucher.added.waitinglist").exclude(data="")
        qs_le_cnt = qs_le.count()

        total = qs_voucher_cnt + qs_wle_cnt + qs_le_cnt

        slow_update(
            qs_wle,
            name_cached=None,
            name_parts={'_shredded': True},
            email='█',
            phone='█',
            progress_callback=progress_callback,
            progress_offset=0,
            progress_total=total,
        )

        for wle in _progress_helper(qs_voucher, progress_callback, qs_wle_cnt, total):
            if '@' in wle.voucher.comment:
                wle.voucher.comment = '█'
                wle.voucher.save(update_fields=['comment'])

        for le in _progress_helper(qs_le, progress_callback, qs_wle_cnt + qs_voucher_cnt, total):
            d = le.parsed_data
            if 'name' in d:
                d['name'] = '█'
            if 'name_parts' in d:
                d['name_parts'] = {
                    '_legacy': '█'
                }
            d['email'] = '█'
            d['phone'] = '█'
            le.data = json.dumps(d)
            le.shredded = True
            le.save(update_fields=['data', 'shredded'])


class AttendeeInfoShredder(BaseDataShredder):
    verbose_name = _('Attendee info')
    identifier = 'attendee_info'
    description = _('This will remove all attendee names and postal addresses from order positions, as well as logged '
                    'changes to them.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'attendee-info.json', 'application/json', json.dumps({
            '{}-{}'.format(op.order.code, op.positionid): {
                'name': op.attendee_name,
                'company': op.company,
                'street': op.street,
                'zipcode': op.zipcode,
                'city': op.city,
                'country': str(op.country) if op.country else None,
                'state': op.state
            } for op in OrderPosition.all.filter(
                order__event=self.event
            ).filter(
                Q(Q(attendee_name_cached__isnull=False) | Q(attendee_name_parts__isnull=False))
            )
        }, indent=4)

    def shred_data(self, progress_callback=None):
        qs_op = OrderPosition.all.filter(
            order__event=self.event
        ).filter(
            Q(attendee_name_cached__isnull=False) |
            Q(company__isnull=False) |
            Q(street__isnull=False) |
            Q(zipcode__isnull=False) |
            Q(city__isnull=False)
        )
        qs_op_cnt = qs_op.count()

        qs_le = self.event.logentry_set.filter(action_type="pretix.event.order.modified").exclude(data="")
        qs_le_cnt = qs_le.count()

        total = qs_op_cnt + qs_le_cnt

        slow_update(
            qs_op,
            attendee_name_cached=None,
            attendee_name_parts={'_shredded': True},
            company=None,
            street=None,
            zipcode=None,
            city=None,
            progress_callback=progress_callback,
            progress_total=total,
            progress_offset=0,
            # Updates to order position table are slow, since PostgreSQL needs to update many indexes, so let's
            # take them really slowly to not overwhelm the database.
            batch_size=100,
            sleep_time=2,
        )

        for le in _progress_helper(qs_le, progress_callback, qs_op_cnt, total):
            d = le.parsed_data
            if 'data' in d:
                for i, row in enumerate(d['data']):
                    if 'attendee_name' in row:
                        d['data'][i]['attendee_name'] = '█'
                    if 'attendee_name_parts' in row:
                        d['data'][i]['attendee_name_parts'] = {
                            '_legacy': '█'
                        }
                    if 'company' in row:
                        d['data'][i]['company'] = '█'
                    if 'street' in row:
                        d['data'][i]['street'] = '█'
                    if 'zipcode' in row:
                        d['data'][i]['zipcode'] = '█'
                    if 'city' in row:
                        d['data'][i]['city'] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class InvoiceAddressShredder(BaseDataShredder):
    verbose_name = _('Invoice addresses')
    identifier = 'invoice_addresses'
    tax_relevant = True
    description = _('This will remove all invoice addresses from orders, as well as logged changes to them.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        yield 'invoice-addresses.json', 'application/json', json.dumps({
            ia.order.code: InvoiceAddressSerializer(ia).data
            for ia in InvoiceAddress.objects.filter(order__event=self.event)
        }, indent=4)

    def shred_data(self, progress_callback=None):
        qs_ia = InvoiceAddress.objects.filter(order__event=self.event)
        qs_ia_cnt = qs_ia.count()

        qs_le = self.event.logentry_set.filter(action_type="pretix.event.order.modified").exclude(data="")
        qs_le_cnt = qs_le.count()

        total = qs_ia_cnt + qs_le_cnt

        slow_delete(qs_ia, progress_callback=progress_callback, progress_total=total, progress_offset=0)

        for le in _progress_helper(qs_le, progress_callback, qs_ia_cnt, total):
            d = le.parsed_data
            if 'invoice_data' in d and not isinstance(d['invoice_data'], bool):
                for field in d['invoice_data']:
                    if d['invoice_data'][field]:
                        d['invoice_data'][field] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class QuestionAnswerShredder(BaseDataShredder):
    verbose_name = _('Question answers')
    identifier = 'question_answers'
    description = _('This will remove all answers to questions, as well as logged changes to them.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        d = {}
        for op in OrderPosition.all.filter(order__event=self.event).prefetch_related('answers', 'answers__question'):
            for a in op.answers.all():
                if a.file:
                    fname = f'{op.order.code}-{op.positionid}-{a.question.identifier}-{os.path.basename(a.file.name)}'
                    yield fname, 'application/unknown', a.file.read()
            d[f'{op.order.code}-{op.positionid}'] = AnswerSerializer(
                sorted(op.answers.all(), key=lambda a: a.question_id), context={'request': None}, many=True
            ).data
        yield 'question-answers.json', 'application/json', json.dumps(d, indent=4)

    def shred_data(self, progress_callback=None):
        qs_qa = QuestionAnswer.objects.filter(orderposition__order__event=self.event)
        qs_qa_cnt = qs_qa.count()

        qs_le = self.event.logentry_set.filter(action_type="pretix.event.order.modified").exclude(data="")
        qs_le_cnt = qs_le.count()

        total = qs_qa_cnt + qs_le_cnt

        slow_delete(qs_qa, progress_callback=progress_callback, progress_total=total, progress_offset=0)

        for le in _progress_helper(qs_le, progress_callback, qs_qa_cnt, total):
            d = le.parsed_data
            if 'data' in d:
                for i, row in enumerate(d['data']):
                    if isinstance(d['data'], list):
                        for f in row:
                            if f not in ('attendee_name', 'attendee_email'):
                                d['data'][i][f] = '█'
                le.data = json.dumps(d)
                le.shredded = True
                le.save(update_fields=['data', 'shredded'])


class InvoiceShredder(BaseDataShredder):
    verbose_name = _('Invoices')
    identifier = 'invoices'
    tax_relevant = True
    description = _('This will remove all invoice PDFs, as well as any of their text content that might contain '
                    'personal data from the database. Invoice numbers and totals will be conserved.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        for i in self.event.invoices.filter(shredded=False):
            if not i.file:
                invoice_pdf_task.apply(args=(i.pk,))
                i.refresh_from_db()
            i.file.open('rb')
            yield 'invoices/{}.pdf'.format(i.number), 'application/pdf', i.file.read()
            i.file.close()

    def shred_data(self, progress_callback=None):
        qs_i = self.event.invoices.filter(shredded=False)
        total = qs_i.count()

        for i in _progress_helper(qs_i, progress_callback, 0, total):
            if i.file:
                i.file.delete()
                i.shredded = True
                i.introductory_text = "█"
                i.additional_text = "█"
                i.invoice_to = "█"
                i.payment_provider_text = "█"
                i.save()
                i.lines.update(description="█")


class CachedTicketShredder(BaseDataShredder):
    verbose_name = _('Cached ticket files')
    identifier = 'cachedtickets'
    description = _('This will remove all cached ticket files. No download will be offered.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        pass

    def shred_data(self, progress_callback=None):
        qs_1 = CachedTicket.objects.filter(order_position__order__event=self.event)
        qs_1_cnt = qs_1.count()

        qs_2 = CachedCombinedTicket.objects.filter(order__event=self.event)
        qs_2_cnt = qs_2.count()

        total = qs_1_cnt + qs_2_cnt

        slow_delete(qs_1, progress_callback=progress_callback, progress_total=total, progress_offset=0)
        slow_delete(qs_2, progress_callback=progress_callback, progress_total=total, progress_offset=qs_1_cnt)


class PaymentInfoShredder(BaseDataShredder):
    verbose_name = _('Payment information')
    identifier = 'payment_info'
    tax_relevant = True
    description = _('This will remove payment-related information. Depending on the payment method, all data will be '
                    'removed or personal data only. No download will be offered.')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        pass

    def shred_data(self, progress_callback=None):
        qs_p = OrderPayment.objects.filter(order__event=self.event)
        qs_p_count = qs_p.count()
        qs_r = OrderRefund.objects.filter(order__event=self.event)
        qs_r_count = qs_r.count()

        total = qs_p_count + qs_r_count

        provs = self.event.get_payment_providers()
        for obj in _progress_helper(qs_p, progress_callback, 0, total):
            pprov = provs.get(obj.provider)
            if pprov:
                pprov.shred_payment_info(obj)

        for obj in _progress_helper(qs_r, progress_callback, qs_p_count, total):
            pprov = provs.get(obj.provider)
            if pprov:
                pprov.shred_payment_info(obj)


@receiver(register_data_shredders, dispatch_uid="shredders_builtin")
def register_core_shredders(sender, **kwargs):
    return [
        EmailAddressShredder,
        PhoneNumberShredder,
        AttendeeInfoShredder,
        InvoiceAddressShredder,
        QuestionAnswerShredder,
        InvoiceShredder,
        CachedTicketShredder,
        PaymentInfoShredder,
        WaitingListShredder
    ]
