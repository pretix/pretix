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

from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _, pgettext, pgettext_lazy

from ..exporter import ListExporter, OrganizerLevelExportMixin
from ..models import ReusableMedium
from ..signals import register_multievent_data_exporters


class ReusableMediaExporter(OrganizerLevelExportMixin, ListExporter):
    identifier = 'reusablemedia'
    verbose_name = _('Reusable media')
    category = pgettext_lazy('export_category', 'Reusable media')
    description = _('Download a spread sheet with the data of all reusable medias on your account.')
    repeatable_read = False

    def iterate_list(self, form_data):
        media = ReusableMedium.objects.filter(
            organizer=self.organizer,
        ).select_related(
            'customer', 'linked_orderposition', 'linked_giftcard',
        ).order_by('created')

        headers = [
            pgettext('reusable_medium', 'Media type'),
            pgettext('reusable_medium', 'Identifier'),
            _('Active'),
            _('Expiration date'),
            _('Customer account'),
            _('Linked ticket'),
            _('Linked gift card'),
            _('Notes'),
        ]

        yield headers
        yield self.ProgressSetTotal(total=media.count())

        for medium in media.iterator(chunk_size=1000):
            row = [
                medium.type,
                medium.identifier,
                _('Yes') if medium.active else _('No'),
                date_format(medium.expires, 'SHORT_DATETIME_FORMAT') if medium.expires else '',
                medium.customer.identifier if medium.customer_id else '',
                f"{medium.linked_orderposition.order.code}-{medium.linked_orderposition.positionid}" if medium.linked_orderposition_id else '',
                medium.linked_giftcard.secret if medium.linked_giftcard_id else '',
                medium.notes,
            ]
            yield row

    def get_filename(self):
        return f'{self.organizer.slug}_media'


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_reusablemedia")
def register_multievent_i_reusable_media_exporter(sender, **kwargs):
    return ReusableMediaExporter
