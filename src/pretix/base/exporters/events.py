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

from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from ...control.forms.filter import get_all_payment_providers
from ..exporter import ListExporter
from ..signals import register_multievent_data_exporters


class EventDataExporter(ListExporter):
    identifier = 'eventdata'
    verbose_name = _('Event data')
    category = pgettext_lazy('export_category', 'Event data')
    description = _('Download a spreadsheet with information on all events in this organizer account.')

    @cached_property
    def providers(self):
        return dict(get_all_payment_providers())

    def iterate_list(self, form_data):
        header = [
            _("Event name"),
            _("Short form"),
            _("Shop is live"),
            _("Event currency"),
            _("Timezone"),
            _("Event start time"),
            _("Event end time"),
            _("Admission time"),
            _("Start of presale"),
            _("End of presale"),
            _("Location"),
            _("Latitude"),
            _("Longitude"),
            _("Internal comment"),
        ]
        props = list(self.organizer.meta_properties.all())
        for p in props:
            header.append(p.name)
        yield header

        for e in self.events.all():
            m = e.meta_data
            tz = e.timezone
            yield [
                str(e.name),
                e.slug,
                _('Yes') if e.live else _('No'),
                e.currency,
                str(e.timezone),
                date_format(e.date_from.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                date_format(e.date_to.astimezone(tz), 'SHORT_DATETIME_FORMAT') if e.date_to else '',
                date_format(e.date_admission.astimezone(tz), 'SHORT_DATETIME_FORMAT') if e.date_admission else '',
                date_format(e.presale_start.astimezone(tz), 'SHORT_DATETIME_FORMAT') if e.presale_start else '',
                date_format(e.presale_end.astimezone(tz), 'SHORT_DATETIME_FORMAT') if e.presale_end else '',
                str(e.location),
                e.geo_lat or '',
                e.geo_lon or '',
                e.comment,
            ] + [
                m.get(p.name, '') for p in props
            ]

    def get_filename(self):
        return '{}_events'.format(self.organizer.slug)


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_eventdata")
def register_multievent_eventdata_exporter(sender, **kwargs):
    return EventDataExporter
