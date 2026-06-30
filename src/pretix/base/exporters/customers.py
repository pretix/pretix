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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Benjamin Hättasch, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import OrderedDict

from django.dispatch import receiver
from django.utils.timezone import get_current_timezone
from django.utils.translation import gettext as _, gettext_lazy, pgettext_lazy

from pretix.base.settings import PERSON_NAME_SCHEMES

from ..exporter import MultiSheetListExporter, OrganizerLevelExportMixin
from ..models import Membership
from ..signals import register_multievent_data_exporters


class CustomerListExporter(OrganizerLevelExportMixin, MultiSheetListExporter):
    identifier = 'customerlist'
    verbose_name = gettext_lazy('Customer accounts')
    category = pgettext_lazy('export_category', 'Customer accounts')
    description = gettext_lazy('Download a spreadsheet of all currently registered customer accounts.')

    @classmethod
    def get_required_organizer_permission(cls) -> str:
        return 'organizer.customers:write'

    @property
    def sheets(self):
        return (
            ('customers', _('Customers')),
            ('memberships', _('Memberships')),
        )

    @property
    def additional_form_fields(self):
        return OrderedDict(
            []
        )

    def iterate_customers(self, form_data):
        qs = self.organizer.customers.prefetch_related('provider')

        headers = [
            _('Customer ID'),
            _('SSO provider'),
            _('External identifier'),
            _('Email'),
            _('Phone number'),
            _('Full name'),
        ]
        name_scheme = PERSON_NAME_SCHEMES[self.organizer.settings.name_scheme]
        if name_scheme and len(name_scheme['fields']) > 1:
            for k, label, w in name_scheme['fields']:
                headers.append(_('Name') + ': ' + str(label))

        headers += [
            _('Account active'),
            _('Verified email address'),
            _('Last login'),
            _('Registration date'),
            _('Language'),
            _('Notes'),
        ]
        yield headers

        tz = get_current_timezone()
        for obj in qs:
            row = [
                obj.identifier,
                obj.provider.name if obj.provider else None,
                obj.external_identifier,
                obj.email or '',
                obj.phone or '',
                obj.name,
            ]
            if name_scheme and len(name_scheme['fields']) > 1:
                for k, label, w in name_scheme['fields']:
                    row.append(obj.name_parts.get(k, ''))
            row += [
                _('Yes') if obj.is_active else _('No'),
                _('Yes') if obj.is_verified else _('No'),
                obj.last_login.astimezone(tz).date().strftime('%Y-%m-%d') if obj.last_login else '',
                obj.date_joined.astimezone(tz).date().strftime('%Y-%m-%d') if obj.date_joined else '',
                obj.get_locale_display(),
                obj.notes or '',
            ]
            yield row

    def iterate_memberships(self, form_data):
        qs = Membership.objects.filter(
            customer__organizer=self.organizer
        ).prefetch_related('membership_type').select_related('customer', 'granted_in', 'granted_in__order')

        headers = [
            _('Customer ID'),
            _('External identifier'),
            _('Email'),
            _('Test mode'),
            _('Canceled'),
            _('Membership type'),
            _('Purchase ticket'),
            _('Start date'),
            _('Start time'),
            _('End date'),
            _('End time'),
            _('Name'),
        ]
        name_scheme = PERSON_NAME_SCHEMES[self.organizer.settings.name_scheme]
        if name_scheme and len(name_scheme['fields']) > 1:
            for k, label, w in name_scheme['fields']:
                headers.append(_('Name') + ': ' + str(label))
        yield headers

        tz = get_current_timezone()
        for obj in qs:
            row = [
                obj.customer.identifier,
                obj.customer.external_identifier,
                obj.customer.email or '',
                _('Yes') if obj.testmode else _('No'),
                _('Yes') if obj.canceled else _('No'),
                str(obj.membership_type.name),
                f'{obj.granted_in.order.code}-{obj.granted_in.positionid}' if obj.granted_in else None,
                obj.date_start.astimezone(tz).strftime('%Y-%m-%d'),
                obj.date_start.astimezone(tz).strftime('%H:%M'),
                obj.date_end.astimezone(tz).strftime('%Y-%m-%d'),
                obj.date_end.astimezone(tz).strftime('%H:%M'),
                obj.attendee_name or '',
            ]
            if name_scheme and len(name_scheme['fields']) > 1:
                for k, label, w in name_scheme['fields']:
                    row.append(obj.attendee_name_parts.get(k, ''))
            yield row

    def get_filename(self):
        return '{}_customers'.format(self.organizer.slug)


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_customerlist")
def register_multievent_i_customerlist_exporter(sender, **kwargs):
    return CustomerListExporter
