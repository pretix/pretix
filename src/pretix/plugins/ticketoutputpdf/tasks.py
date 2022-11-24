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

from django.core.files.base import ContentFile

from pretix.base.models import (
    CachedFile, Event, OrderPosition, cachedfile_name,
)
from pretix.base.services.orders import OrderError
from pretix.base.services.tasks import EventTask
from pretix.celery_app import app

from ...base.services.export import ExportError
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
