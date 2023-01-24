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

from django import forms
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView
from oauth2_provider.generators import generate_client_secret
from oauth2_provider.models import get_application_model
from oauth2_provider.scopes import get_scopes_backend
from oauth2_provider.views import (
    ApplicationDelete, ApplicationDetail, ApplicationList,
    ApplicationRegistration, ApplicationUpdate,
)

from pretix.api.models import (
    OAuthAccessToken, OAuthApplication, OAuthRefreshToken,
)
from pretix.control.signals import oauth_application_registered

logger = logging.getLogger(__name__)


class OAuthApplicationListView(ApplicationList):
    template_name = 'pretixcontrol/oauth/app_list.html'

    def get_queryset(self):
        return super().get_queryset().filter(active=True)


class OAuthApplicationRegistrationView(ApplicationRegistration):
    template_name = 'pretixcontrol/oauth/app_register.html'

    def get_form_class(self):
        return forms.modelform_factory(
            get_application_model(),
            fields=(
                "name", "redirect_uris"
            )
        )

    def form_valid(self, form):
        form.instance.client_type = 'confidential'
        form.instance.authorization_grant_type = 'authorization-code'
        secret = generate_client_secret()
        messages.success(self.request, _('Your application has been created and an application secret has been generated. '
                                         'Please copy and save it right now as it will not be shown again: {secret}').format(secret=secret))
        form.instance.client_secret = secret
        oauth_application_registered.send(
            sender=self.request, user=self.request.user, application=form.instance
        )
        return super().form_valid(form)


class ApplicationUpdateForm(forms.ModelForm):
    class Meta:
        model = OAuthApplication
        fields = ("name", "client_id", "redirect_uris")

    def clean_client_id(self):
        return self.instance.client_id

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client_id'].widget.attrs['readonly'] = True


class OAuthApplicationUpdateView(ApplicationUpdate):
    template_name = 'pretixcontrol/oauth/app_update.html'

    def get_form_class(self):
        return ApplicationUpdateForm

    def get_queryset(self):
        return super().get_queryset().filter(active=True)


class OAuthApplicationRollView(ApplicationDetail):
    template_name = 'pretixcontrol/oauth/app_rollkeys.html'

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        secret = generate_client_secret()
        messages.success(request, _('A new client secret has been generated. Please copy and save it right now as '
                                    'it will not be shown again: {secret}').format(secret=secret))
        self.object.client_secret = secret
        self.object.save()
        return HttpResponseRedirect(self.object.get_absolute_url())

    def get_queryset(self):
        return super().get_queryset().filter(active=True)


class OAuthApplicationDeleteView(ApplicationDelete):
    template_name = 'pretixcontrol/oauth/app_delete.html'
    success_url = reverse_lazy("control:user.settings.oauth.apps")

    def get_queryset(self):
        return super().get_queryset().filter(active=True)

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.active = False
        self.object.save()
        return HttpResponseRedirect(self.success_url)

    def form_valid(self, form):
        return self.delete(self.request, self.args, self.kwargs)


class AuthorizationListView(ListView):
    template_name = 'pretixcontrol/oauth/authorized.html'
    context_object_name = 'tokens'

    def get_queryset(self):
        return OAuthAccessToken.objects.filter(
            user=self.request.user
        ).select_related('application').prefetch_related('organizers')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_scopes = get_scopes_backend().get_all_scopes()
        for t in ctx['tokens']:
            t.scopes_descriptions = [all_scopes[scope] for scope in t.scopes]
        return ctx


class AuthorizationRevokeView(DetailView):
    template_name = 'pretixcontrol/oauth/auth_revoke.html'
    success_url = reverse_lazy("control:user.settings.oauth.list")

    def get_queryset(self):
        return OAuthAccessToken.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['application'] = self.get_object().application
        return ctx

    def post(self, request, *args, **kwargs):
        o = self.get_object()
        for rt in OAuthRefreshToken.objects.filter(access_token=o):
            rt.revoke()
        o.delete()

        messages.success(request, _('Access for the selected application has been revoked.'))
        return redirect(self.success_url)
