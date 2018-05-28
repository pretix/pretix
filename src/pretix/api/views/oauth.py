import logging

from django import forms
from django.conf import settings
from oauth2_provider.exceptions import OAuthToolkitError
from oauth2_provider.forms import AllowForm
from oauth2_provider.views import (
    AuthorizationView as BaseAuthorizationView,
    IntrospectTokenView as BaseIntrospectTokenView,
    RevokeTokenView as BaseRevokeTokenView, TokenView as BaseTokenView,
)

from pretix.base.models import OAuthApplication, Organizer

logger = logging.getLogger(__name__)


class OAuthAllowForm(AllowForm):
    organizers = forms.ModelMultipleChoiceField(
        queryset=Organizer.objects.none(),
        widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['organizers'].queryset = Organizer.objects.filter(
            pk__in=user.teams.values_list('organizer', flat=True))


class AuthorizationView(BaseAuthorizationView):
    template_name = "pretixcontrol/auth/oauth_authorization.html"
    form_class = OAuthAllowForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['settings'] = settings
        return ctx

    def create_authorization_response(self, request, scopes, credentials, allow, organizers):
        credentials["organizers"] = organizers
        return super().create_authorization_response(request, scopes, credentials, allow)

    def form_valid(self, form):
        client_id = form.cleaned_data["client_id"]
        application = OAuthApplication.objects.get(client_id=client_id)
        credentials = {
            "client_id": form.cleaned_data.get("client_id"),
            "redirect_uri": form.cleaned_data.get("redirect_uri"),
            "response_type": form.cleaned_data.get("response_type", None),
            "state": form.cleaned_data.get("state", None),
        }
        scopes = form.cleaned_data.get("scope")
        allow = form.cleaned_data.get("allow")

        try:
            uri, headers, body, status = self.create_authorization_response(
                request=self.request, scopes=scopes, credentials=credentials, allow=allow,
                organizers=form.cleaned_data.get("organizers")
            )
        except OAuthToolkitError as error:
            return self.error_response(error, application)

        self.success_url = uri
        logger.debug("Success url for the request: {0}".format(self.success_url))
        return self.redirect(self.success_url, application)


class TokenView(BaseTokenView):
    pass


class RevokeTokenView(BaseRevokeTokenView):
    pass


class IntrospectTokenView(BaseIntrospectTokenView):
    pass
