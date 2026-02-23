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
# This file contains Apache-licensed contributions copyrighted by: Alexander Schwartz
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import csv
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from pretix.base.models import CachedFile
from pretix.base.services.modelimport import (
    import_orders, import_vouchers, parse_csv,
)
from pretix.base.views.tasks import AsyncAction
from pretix.control.forms.modelimport import (
    OrdersProcessForm, VouchersProcessForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.http import redirect_to_url

logger = logging.getLogger(__name__)
ENCODINGS = (
    "utf8", "utf16", "utf32",
    "iso-8859-1", "iso-8859-2", "iso-8859-3", "iso-8859-4", "iso-8859-5", "iso-8859-6", "iso-8859-7",
    "iso-8859-8", "iso-8859-9", "iso-8859-10", "iso-8859-11", "iso-8859-12", "iso-8859-13", "iso-8859-14",
    "iso-8859-15", "iso-8859-16",
    "maccyrillic", "macgreek", "maciceland", "maclatin2", "macroman", "macturkish",
    "windows-1250", "windows-1251", "windows-1252", "windows-1253", "windows-1254", "windows-1255",
    "windows-1256", "windows-1257", "windows-1258"
)


class BaseImportView(TemplateView):
    def post(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            return redirect_to_url(request.path)
        if not request.FILES['file'].name.lower().endswith('.csv'):
            messages.error(request, _('Please only upload CSV files.'))
            return redirect_to_url(request.path)
        if request.FILES['file'].size > settings.FILE_UPLOAD_MAX_SIZE_OTHER:
            messages.error(request, _('Please do not upload files larger than 10 MB.'))
            return redirect_to_url(request.path)

        cf = CachedFile.objects.create(
            expires=now() + timedelta(days=1),
            date=now(),
            filename='import.csv',
            type='text/csv',
        )
        cf.bind_to_session(request, "modelimport")
        cf.file.save('import.csv', request.FILES['file'])

        if self.request.POST.get("charset") in ENCODINGS:
            charset = self.request.POST.get("charset")
        else:
            charset = "auto"

        return redirect(self.get_process_url(request, cf, charset))

    def get_context_data(self, **kwargs):
        return super().get_context_data(encodings=ENCODINGS)

    def get_process_url(self, request, cf, charset):
        raise NotImplementedError()  # noqa


class BaseProcessView(AsyncAction, FormView):
    known_errortypes = ['DataImportError']

    @property
    def settings_key(self):
        raise NotImplementedError()  # noqa

    @property
    def settings_holder(self):
        raise NotImplementedError()  # noqa

    def get_form_kwargs(self):
        k = super().get_form_kwargs()
        k.update({
            'initial': self.settings_holder.settings.get(self.settings_key, as_type=dict),
            'headers': self.parsed.fieldnames
        })
        return k

    def form_valid(self, form):
        self.settings_holder.settings.set(self.settings_key, form.cleaned_data)
        if self.request.GET.get("charset") in ENCODINGS:
            charset = self.request.GET.get("charset")
        else:
            charset = None
        return self.do(
            self.settings_holder.pk,
            self.file.id,
            form.cleaned_data,
            self.request.LANGUAGE_CODE,
            self.request.user.pk,
            charset,
        )

    @cached_property
    def file(self):
        cf = get_object_or_404(CachedFile, pk=self.kwargs.get("file"), filename="import.csv")
        if not cf.allowed_for_session(self.request, "modelimport"):
            raise Http404()
        return cf

    @cached_property
    def parsed(self):
        if self.request.GET.get("charset") in ENCODINGS:
            charset = self.request.GET.get("charset")
        else:
            charset = None
        try:
            reader = parse_csv(self.file.file, 1024 * 1024, charset=charset)
        except UnicodeDecodeError:
            messages.warning(
                self.request,
                _(
                    "We could not identify the character encoding of the CSV file. "
                    "Some characters were replaced with a placeholder."
                )
            )
            reader = parse_csv(self.file.file, 1024 * 1024, "replace", charset=charset)
        if reader and reader._had_duplicates:
            messages.warning(
                self.request,
                _(
                    "Multiple columns of the CSV file have the same name and were renamed automatically. We "
                    "recommend that you rename these in your source file to avoid problems during import."
                )
            )
        return reader

    @cached_property
    def parsed_list(self):
        try:
            return list(self.parsed)
        except csv.Error:
            logger.exception("Could not parse full CSV file")
            return None

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return FormView.get(self, request, *args, **kwargs)

    def get_success_message(self, value):
        return _('The import was successful.')

    def get_success_url(self, value):
        raise NotImplementedError()  # noqa

    def get_form_url(self):
        raise NotImplementedError()  # noqa

    def dispatch(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        if not self.parsed or not self.parsed_list:
            messages.error(request, _('We\'ve been unable to parse the uploaded file as a CSV file.'))
            return redirect(self.get_form_url())
        return super().dispatch(request, *args, **kwargs)

    def get_error_url(self):
        return self.request.path

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['file'] = self.file
        ctx['parsed'] = self.parsed
        ctx['sample_rows'] = self.parsed_list[:3]
        return ctx


class OrderImportView(EventPermissionRequiredMixin, BaseImportView):
    template_name = 'pretixcontrol/orders/import_start.html'
    permission = 'can_change_orders'

    def get_process_url(self, request, cf, charset):
        return reverse('control:event.orders.import.process', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
            'file': cf.id
        }) + "?charset=" + charset


class OrderProcessView(EventPermissionRequiredMixin, BaseProcessView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/orders/import_process.html'
    form_class = OrdersProcessForm
    task = import_orders
    settings_key = 'order_import_settings'

    @property
    def settings_holder(self):
        return self.request.event

    def get_form_kwargs(self):
        k = super().get_form_kwargs()
        k.update({
            'event': self.request.event,
        })
        return k

    def get_form_url(self):
        return reverse('control:event.orders.import', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
        })

    def get_success_url(self, value):
        return reverse('control:event.orders', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
        })


class VoucherImportView(EventPermissionRequiredMixin, BaseImportView):
    template_name = 'pretixcontrol/vouchers/import_start.html'
    permission = 'can_change_vouchers'

    def get_process_url(self, request, cf, charset):
        return reverse('control:event.vouchers.import.process', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
            'file': cf.id
        }) + "?charset=" + charset


class VoucherProcessView(EventPermissionRequiredMixin, BaseProcessView):
    permission = 'can_change_vouchers'
    template_name = 'pretixcontrol/vouchers/import_process.html'
    form_class = VouchersProcessForm
    task = import_vouchers
    settings_key = 'voucher_import_settings'

    @property
    def settings_holder(self):
        return self.request.event

    def get_form_kwargs(self):
        k = super().get_form_kwargs()
        k.update({
            'event': self.request.event,
        })
        return k

    def get_form_url(self):
        return reverse('control:event.vouchers.import', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
        })

    def get_success_url(self, value):
        return reverse('control:event.vouchers', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
        })
