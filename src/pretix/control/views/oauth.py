import logging

from django import forms
from django.contrib import messages
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _
from django.views.generic import ListView
from oauth2_provider.generators import generate_client_secret
from oauth2_provider.models import get_application_model
from oauth2_provider.views import (
    ApplicationDelete, ApplicationDetail, ApplicationList,
    ApplicationRegistration, ApplicationUpdate,
)

from pretix.base.models import OAuthApplication, OAuthRefreshToken

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
        return super().form_valid(form)


class ApplicationUpdateForm(forms.ModelForm):
    class Meta:
        model = OAuthApplication
        fields = ("name", "client_id", "client_secret", "redirect_uris")

    def clean_client_id(self):
        return self.instance.client_id

    def clean_client_secret(self):
        return self.instance.client_secret

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client_id'].widget.attrs['readonly'] = True
        self.fields['client_secret'].widget.attrs['readonly'] = True


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
        messages.success(request, _('A new client secret has been generated and is now effective.'))
        self.object.client_secret = generate_client_secret()
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


class AuthorizationListView(ListView):
    template_name = 'pretixcontrol/oauth/authorized.html'

    def get_queryset(self):
        has_refresh_token = OAuthRefreshToken.objects.filter(
            user=self.request.user,
            application_id=OuterRef('pk'),
            revoked__isnull=True
        )
        return OAuthApplication.objects.annotate(has_rt=Exists(has_refresh_token)).filter(
            Q(has_rt=True) | Q(oauthaccesstoken__user=self.request.user)
        ).distinct()
