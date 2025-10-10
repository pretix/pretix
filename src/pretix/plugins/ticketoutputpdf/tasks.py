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
import json
import logging
from io import BytesIO

from django.core.files.base import ContentFile
from django.db.models import Prefetch, prefetch_related_objects
from pypdf import PdfWriter

from pretix.base.models import (
    CachedFile, Checkin, Event, EventMetaValue, ItemMetaValue,
    ItemVariationMetaValue, OrderPosition, SalesChannel, SubEventMetaValue,
    cachedfile_name,
)
from pretix.base.services.orders import OrderError
from pretix.base.services.tasks import EventTask
from pretix.celery_app import app

from ...base.i18n import language
from ...base.services.export import ExportError
from .models import TicketLayout
from .ticketoutput import PdfTicketOutput

logger = logging.getLogger(__name__)


@app.task(base=EventTask, throws=(OrderError, ExportError,))
def tickets_create_pdf(event: Event, fileid: int, position: int, channel) -> int:
    file = CachedFile.objects.get(id=fileid)
    position = OrderPosition.all.get(id=position)

    o = PdfTicketOutput(event, override_channel=channel)
    _, _, data = o.generate(position)
    file.file.save(cachedfile_name(file, file.filename), ContentFile(data))
    file.save()
    return file.pk


@app.task(base=EventTask, throws=(OrderError, ExportError,))
def bulk_render(event: Event, fileid: int, parts: list) -> int:
    file = CachedFile.objects.get(id=fileid)

    channels = SalesChannel.objects.in_bulk([p["override_channel"] for p in parts if p.get("override_channel")])
    layouts = TicketLayout.objects.in_bulk([p["override_layout"] for p in parts if p.get("override_layout")])

    positions = OrderPosition.objects.all()
    prefetch_related_objects([event.organizer], 'meta_properties')
    prefetch_related_objects(
        [event],
        Prefetch('meta_values', queryset=EventMetaValue.objects.select_related('property'),
                 to_attr='meta_values_cached'),
        'questions',
        'item_meta_properties',
    )
    positions = positions.prefetch_related(
        Prefetch('checkins', queryset=Checkin.objects.select_related("device")),
        Prefetch('item', queryset=event.items.prefetch_related(
            Prefetch('meta_values', ItemMetaValue.objects.select_related('property'),
                     to_attr='meta_values_cached')
        )),
        'variation',
        'answers', 'answers__options', 'answers__question',
        'item__category',
        'addon_to__answers', 'addon_to__answers__options', 'addon_to__answers__question',
        Prefetch('addons', positions.select_related('item', 'variation')),
        Prefetch('subevent', queryset=event.subevents.prefetch_related(
            Prefetch('meta_values', to_attr='meta_values_cached',
                     queryset=SubEventMetaValue.objects.select_related('property'))
        )),
        'linked_media',
        Prefetch('order', event.orders.select_related('invoice_address').prefetch_related(
            Prefetch(
                'positions',
                positions.prefetch_related(
                    Prefetch('checkins', queryset=Checkin.objects.select_related('device')),
                    Prefetch('item', queryset=event.items.prefetch_related(
                        Prefetch('meta_values', ItemMetaValue.objects.select_related('property'),
                                 to_attr='meta_values_cached')
                    )),
                    Prefetch('variation', queryset=event.items.prefetch_related(
                        Prefetch('meta_values', ItemVariationMetaValue.objects.select_related('property'),
                                 to_attr='meta_values_cached')
                    )),
                    'answers', 'answers__options', 'answers__question',
                    'item__category',
                    Prefetch('subevent', queryset=event.subevents.prefetch_related(
                        Prefetch('meta_values', to_attr='meta_values_cached',
                                 queryset=SubEventMetaValue.objects.select_related('property'))
                    )),
                    Prefetch('addons', positions.select_related('item', 'variation', 'seat'))
                ).select_related('addon_to', 'seat', 'addon_to__seat')
            )
        ))
    ).select_related(
        'addon_to', 'seat', 'addon_to__seat'
    )
    positions = positions.in_bulk([p["orderposition"] for p in parts])

    merger = PdfWriter()
    for part in parts:
        p = positions[part["orderposition"]]
        p.order.event = event  # performance optimization
        with (language(p.order.locale)):
            kwargs = {}
            if part.get("override_channel"):
                kwargs["override_channel"] = channels[part["override_channel"]].identifier
            if part.get("override_layout"):
                l = layouts[part["override_layout"]]
                kwargs["override_layout"] = json.loads(l.layout)
                kwargs["override_background"] = l.background
            prov = PdfTicketOutput(
                event,
                **kwargs,
            )
            filename, ctype, data = prov.generate(p)
            merger.append(ContentFile(data))

    outbuffer = BytesIO()
    merger.write(outbuffer)
    merger.close()
    outbuffer.seek(0)

    file.type = "application/pdf"
    file.file.save(cachedfile_name(file, file.filename), ContentFile(outbuffer.getvalue()))
    file.save()
    return file.pk
