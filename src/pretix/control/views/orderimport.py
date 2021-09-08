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
# This file contains Apache-licensed contributions copyrighted by: Alexander Schwartz
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from pretix.base.models import CachedFile
from pretix.base.services.orderimport import import_orders, parse_csv
from pretix.base.views.tasks import AsyncAction
from pretix.control.forms.orderimport import ProcessForm
from pretix.control.permissions import EventPermissionRequiredMixin

logger = logging.getLogger(__name__)


class ImportView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/orders/import_start.html'
    permission = 'can_change_orders'

    def post(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))
        if not request.FILES['file'].name.lower().endswith('.csv'):
            messages.error(request, _('Please only upload CSV files.'))
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))
        if request.FILES['file'].size > settings.FILE_UPLOAD_MAX_SIZE_OTHER:
            messages.error(request, _('Please do not upload files larger than 10 MB.'))
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))

        cf = CachedFile.objects.create(
            expires=now() + timedelta(days=1),
            date=now(),
            filename='import.csv',
            type='text/csv',
        )
        cf.file.save('import.csv', request.FILES['file'])
        return redirect(reverse('control:event.orders.import.process', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
            'file': cf.id
        }))


class ProcessView(EventPermissionRequiredMixin, AsyncAction, FormView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/orders/import_process.html'
    form_class = ProcessForm
    task = import_orders
    known_errortypes = ['DataImportError']

    def get_form_kwargs(self):
        k = super().get_form_kwargs()
        k.update({
            'event': self.request.event,
            'initial': self.request.event.settings.order_import_settings,
            'headers': self.parsed.fieldnames
        })
        return k

    def form_valid(self, form):
        self.request.event.settings.order_import_settings = form.cleaned_data
        return self.do(
            self.request.event.pk, self.file.id, form.cleaned_data, self.request.LANGUAGE_CODE,
            self.request.user.pk
        )

    @cached_property
    def file(self):
        return get_object_or_404(CachedFile, pk=self.kwargs.get("file"), filename="import.csv")

    @cached_property
    def parsed(self):
        try:
            return parse_csv(self.file.file, 1024 * 1024)
        except UnicodeDecodeError:
            messages.warning(
                self.request,
                _(
                    "We could not identify the character encoding of the CSV file. "
                    "Some characters were replaced with a placeholder."
                )
            )
            return parse_csv(self.file.file, 1024 * 1024, "replace")

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return FormView.get(self, request, *args, **kwargs)

    def get_success_message(self, value):
        return _('The import was successful.')

    def get_success_url(self, value):
        return reverse('control:event.orders', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
        })

    def dispatch(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        if not self.parsed:
            messages.error(request, _('We\'ve been unable to parse the uploaded file as a CSV file.'))
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))
        return super().dispatch(request, *args, **kwargs)

    def get_error_url(self):
        return reverse('control:event.orders.import.process', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
            'file': self.file.id
        })

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['file'] = self.file
        ctx['parsed'] = self.parsed
        ctx['sample_rows'] = list(self.parsed)[:3]
        return ctx
