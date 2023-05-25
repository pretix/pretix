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
from django.utils.translation import gettext
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Event, LogEntry, User, Voucher
from pretix.base.services.mail import mail


def vouchers_send(event: Event, vouchers: list, subject: str, message: str, recipients: list, user: int,
                  progress=None) -> None:
    vouchers = list(Voucher.objects.filter(id__in=vouchers).order_by('id'))
    user = User.objects.get(pk=user)
    for ir, r in enumerate(recipients):
        voucher_list = []
        for i in range(r['number']):
            voucher_list.append(vouchers.pop(0))
        with language(event.settings.locale):
            email_context = get_email_context(event=event, name=r.get('name') or '',
                                              voucher_list=[v.code for v in voucher_list])
            mail(
                r['email'],
                subject,
                LazyI18nString(message),
                email_context,
                event,
                locale=event.settings.locale,
            )
            logs = []
            for v in voucher_list:
                if r.get('tag') and r.get('tag') != v.tag:
                    v.tag = r.get('tag')
                if v.comment:
                    v.comment += '\n\n'
                v.comment = gettext('The voucher has been sent to {recipient}.').format(recipient=r['email'])
                logs.append(v.log_action(
                    'pretix.voucher.sent',
                    user=user,
                    data={
                        'recipient': r['email'],
                        'name': r.get('name'),
                        'subject': subject,
                        'message': message,
                    },
                    save=False
                ))
            Voucher.objects.bulk_update(voucher_list, fields=['comment', 'tag'], batch_size=500)
            LogEntry.objects.bulk_create(logs, batch_size=500)

            if progress and ir % 50 == 0:
                progress(ir / len(recipients))
