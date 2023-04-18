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
import importlib_metadata as metadata
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

from pretix.base.models import LogEntry, OrderPayment, OrderRefund
from pretix.base.services.update_check import check_result_table, update_check
from pretix.base.settings import GlobalSettingsObject
from pretix.control.forms.global_settings import (
    GlobalSettingsForm, LicenseCheckForm, UpdateSettingsForm,
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


class LicenseCheckView(StaffMemberRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_license.html'
    form_class = LicenseCheckForm

    def get_initial(self):
        d = {}
        gs = GlobalSettingsObject()
        d.update(gs.settings.license_check_input)
        if not d:
            d['source_notice'] = 'pretix (AGPLv3 with additional terms): https://github.com/pretix/pretix'
            seen = set()
            for entry_point in metadata.entry_points(group='pretix.plugin'):
                if entry_point.dist.name not in seen:
                    try:
                        license, url = self._get_license_for_pkg(entry_point.dist.name)
                    except FileNotFoundError:
                        license, url = '?', '?'
                    d['source_notice'] += f'\n{entry_point.dist.name} ({license}): {url}'
                    seen.add(entry_point.dist.name)

        return d

    def form_valid(self, form):
        gs = GlobalSettingsObject()
        gs.settings.license_check_input = form.cleaned_data
        gs.settings.license_check_completed = now()
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes have not been saved, see below for errors.'))
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('control:global.license')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        input = self.get_initial()
        if 'base_license' in input:
            ctx['results'] = self._check_results(input)
        else:
            ctx['results'] = False
        return ctx

    def _get_license_for_pkg(self, pkg):
        license, url = None, None
        try:
            pkg = metadata.distribution(pkg)
        except:
            return None, None
        try:
            for k, v in pkg.metadata.items():
                if k == "License":
                    license = v
                if k == "Home-page":
                    url = v
        except FileNotFoundError:
            license = '?'
            url = '?'
        return license, url

    def _check_results(self, input):
        res = []

        if input.get('base_license') == 'agpl_addperm' and input.get('usage') != 'internally':
            res.append((
                'danger', 'exclamation-circle',
                _('You are in violation of the license. If you\'re not sure whether you qualify for the additional '
                  'permission or if you offer the functionality of pretix to others, you must either use pretix under '
                  'AGPLv3 terms or obtain a pretix Enterprise license.')
            ))

        if (input.get('base_license') != 'agpl' or input.get('plugins_enterprise')) and input.get('plugins_copyleft'):
            res.append((
                'danger', 'exclamation-circle',
                _('You may not make use of the additional permission or of a pretix Enterprise license if you install '
                  'any plugins licensed with strong copyleft, otherwise you are likely in violation of the license '
                  'of these plugins.')
            ))

        if input.get('base_license') == 'agpl' and not input.get('source_notice'):
            res.append((
                'danger', 'exclamation-circle',
                _('If you\'re using pretix under AGPL license, you need to provide instructions on how to access the '
                  'source code.')
            ))

        if input.get('base_license') == 'agpl' and input.get('plugins_enterprise'):
            res.append((
                'danger', 'exclamation-circle',
                _('You must not use pretix under AGPL terms if you use pretix Enterprise plugins.')
            ))

        if input.get('base_license') not in ('enterprise', 'agpl_addperm'):
            if input.get('base_changes') == 'yes':
                res.append((
                    'warning', 'warning',
                    _('You need to make all changes you made to pretix\' source code freely available to every visitor '
                      'of your site in source code form under the same license terms as pretix (AGPLv3 + additional '
                      'restrictions). Make sure to keep it up to date!')
                ))
            if input.get('plugins_own'):
                res.append((
                    'warning', 'warning',
                    _('You need to make all your installed plugins freely available to every visitor '
                      'of your site in source code form under the same license terms as pretix (AGPLv3 + additional '
                      'restrictions). Make sure to keep it up to date!')
                ))

        for entry_point in metadata.entry_points(group='pretix.plugin'):
            license, url = self._get_license_for_pkg(entry_point.dist.name)

            if not license or not any(l in license for l in ('Apache', 'MIT', 'BSD', 'pretix Enterprise', 'GPL')):
                res.append((
                    'muted', 'warning',
                    _('We found the plugin "{plugin}" with license "{license}" which this tool does not know about and '
                      'therefore cannot give any recommendations.').format(plugin=entry_point.dist.name, license=license)
                ))
                continue

            if not input.get('plugins_enterprise') and 'pretix Enterprise' in license:
                res.append((
                    'danger', 'exclamation-circle',
                    _('You selected that you have no active pretix Enterprise licenses, but we found the following '
                      'Enterprise plugin: {plugin}').format(plugin=entry_point.dist.name)
                ))

            if not input.get('plugins_copyleft') and any(l in license for l in ('GPL',)):
                res.append((
                    'danger', 'exclamation-circle',
                    _('You selected that you have no copyleft-licensed plugins installed, but we found the '
                      'plugin "{plugin}" with license "{license}".').format(plugin=entry_point.dist.name, license=license)
                ))

            if not input.get('plugins_free') and any(l in license for l in ('Apache', 'MIT', 'BSD')):
                res.append((
                    'danger', 'exclamation-circle',
                    _('You selected that you have no free plugins installed, but we found the '
                      'plugin "{plugin}" with license "{license}".').format(plugin=entry_point.dist.name, license=license)
                ))

        return res
