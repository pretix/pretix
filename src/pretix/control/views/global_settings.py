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

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

from pretix.base.models import LogEntry, OrderPayment, OrderRefund
from pretix.base.services.update_check import check_result_table, update_check
from pretix.base.settings import GlobalSettingsObject
from pretix.control.forms.global_settings import (
    GlobalSettingsForm, UpdateSettingsForm,
)
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, StaffMemberRequiredMixin,
)


class GlobalSettingsView(AdministratorPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_settings.html'
    form_class = GlobalSettingsForm

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes have not been saved, see below for errors.'))
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('control:global.settings')


class UpdateCheckView(StaffMemberRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_update.html'
    form_class = UpdateSettingsForm

    def post(self, request, *args, **kwargs):
        if 'trigger' in request.POST:
            update_check.apply()
            return redirect(self.get_success_url())
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes have not been saved, see below for errors.'))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['gs'] = GlobalSettingsObject()
        ctx['gs'].settings.set('update_check_ack', True)
        ctx['tbl'] = check_result_table()
        return ctx

    def get_success_url(self):
        return reverse('control:global.update')


class MessageView(TemplateView):
    template_name = 'pretixcontrol/global_message.html'


class LogDetailView(AdministratorPermissionRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        le = get_object_or_404(LogEntry, pk=request.GET.get('pk'))
        return JsonResponse({'data': le.parsed_data})


class PaymentDetailView(AdministratorPermissionRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        p = get_object_or_404(OrderPayment, pk=request.GET.get('pk'))
        return JsonResponse({'data': p.info_data})


class RefundDetailView(AdministratorPermissionRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        p = get_object_or_404(OrderRefund, pk=request.GET.get('pk'))
        return JsonResponse({'data': p.info_data})
