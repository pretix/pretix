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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.models import OrderPosition

from ..exporter import BaseExporter
from ..models import Order
from ..signals import (
    register_data_exporters, register_multievent_data_exporters,
)


class MailExporter(BaseExporter):
    identifier = 'mailaddrs'
    verbose_name = _('Email addresses (text file)')
    category = pgettext_lazy('export_category', 'Order data')
    description = _("Download a text file with all email addresses collected either from buyers or from ticket holders.")

    def render(self, form_data: dict):
        qs = Order.objects.filter(event__in=self.events, status__in=form_data['status']).prefetch_related('event')
        addrs = qs.values('email')
        pos = OrderPosition.objects.filter(
            order__event__in=self.events, order__status__in=form_data['status']
        ).values('attendee_email')
        data = "\r\n".join(set(a['email'] for a in addrs if a['email'])
                           | set(a['attendee_email'] for a in pos if a['attendee_email']))

        if self.is_multievent:
            return '{}_pretixemails.txt'.format(self.organizer.slug), 'text/plain', data.encode("utf-8")
        else:
            return '{}_pretixemails.txt'.format(self.event.slug), 'text/plain', data.encode("utf-8")

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('status',
                 forms.MultipleChoiceField(
                     label=_('Filter by status'),
                     initial=[Order.STATUS_PENDING, Order.STATUS_PAID],
                     choices=Order.STATUS_CHOICE,
                     widget=forms.CheckboxSelectMultiple,
                     required=True
                 )),
            ]
        )


@receiver(register_data_exporters, dispatch_uid="exporter_mail")
def register_mail_export(sender, **kwargs):
    return MailExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_mail")
def register_multievent_mail_export(sender, **kwargs):
    return MailExporter
