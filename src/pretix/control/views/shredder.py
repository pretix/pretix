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
# This file contains Apache-licensed contributions copyrighted by: Maico Timmerman
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import logging
from collections import OrderedDict
from zipfile import ZipFile

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import get_language, gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from pretix.base.models import CachedFile
from pretix.base.services.shredder import export, shred
from pretix.base.shredder import ShredError, shred_constraints
from pretix.base.views.tasks import AsyncAction
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views.user import RecentAuthenticationRequiredMixin

logger = logging.getLogger(__name__)


class ShredderMixin:

    @cached_property
    def shredders(self):
        return OrderedDict(
            sorted(self.request.event.get_data_shredders().items(), key=lambda s: s[1].verbose_name)
        )

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except ShredError as e:
            messages.error(request, str(e))
            return redirect(reverse('control:event.shredder.start', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            }))


class StartShredView(RecentAuthenticationRequiredMixin, EventPermissionRequiredMixin, ShredderMixin, TemplateView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/shredder/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['shredders'] = self.shredders
        ctx['constraints'] = shred_constraints(self.request.event)
        return ctx


class ShredDownloadView(RecentAuthenticationRequiredMixin, EventPermissionRequiredMixin, ShredderMixin, TemplateView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/shredder/download.html'

    def get_context_data(self, **kwargs):
        try:
            cf = CachedFile.objects.get(pk=kwargs['file'])
        except CachedFile.DoesNotExist:
            raise ShredError(_("The download file could no longer be found on the server, please try to start again."))

        with ZipFile(cf.file.file, 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())

        if indexdata['organizer'] != kwargs['organizer'] or indexdata['event'] != kwargs['event']:
            raise ShredError(_("This file is from a different event."))

        shredders = []
        for s in indexdata['shredders']:
            shredder = self.shredders.get(s)
            if not shredder:
                continue
            shredders.append(shredder)

        ctx = super().get_context_data(**kwargs)
        ctx['shredders'] = self.shredders
        ctx['download_on_shred'] = any(shredder.require_download_confirmation for shredder in shredders)
        ctx['file'] = get_object_or_404(CachedFile, pk=kwargs.get("file"))
        return ctx


class ShredExportView(RecentAuthenticationRequiredMixin, EventPermissionRequiredMixin, ShredderMixin, AsyncAction, View):
    permission = 'can_change_orders'
    task = export
    known_errortypes = ['ShredError']

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return reverse('control:event.shredder.download', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'file': str(value)
        })

    def get_error_url(self):
        return reverse('control:event.shredder.start', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })

    def post(self, request, *args, **kwargs):
        constr = shred_constraints(self.request.event)
        if constr:
            return self.error(ShredError(self.get_error_url()))

        return self.do(self.request.event.id, request.POST.getlist("shredder"), self.request.session.session_key)


class ShredDoView(RecentAuthenticationRequiredMixin, EventPermissionRequiredMixin, ShredderMixin, AsyncAction, View):
    permission = 'can_change_orders'
    task = shred
    known_errortypes = ['ShredError']

    def get_success_url(self, value):
        return reverse('control:event.shredder.start', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get_success_message(self, value):
        return _('The selected data was deleted successfully.')

    def get_error_url(self):
        if "file" in self.request.POST:
            return reverse('control:event.shredder.download', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug,
                'file': self.request.POST.get("file")
            })
        return reverse('control:event.shredder.start', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })

    def post(self, request, *args, **kwargs):
        constr = shred_constraints(self.request.event)
        if constr:
            return self.error(ShredError(self.get_error_url()))

        if request.event.slug != request.POST.get("slug"):
            return self.error(ShredError(_("The slug you entered was not correct.")))

        return self.do(self.request.event.id, request.POST.get("file"), request.POST.get("confirm_code"),
                       self.request.user.pk, get_language())
