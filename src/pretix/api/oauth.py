from datetime import timedelta

from django.utils import timezone
from oauth2_provider.exceptions import FatalClientError
from oauth2_provider.oauth2_validators import Grant, OAuth2Validator
from oauth2_provider.settings import oauth2_settings


class Validator(OAuth2Validator):

    def save_authorization_code(self, client_id, code, request, *args, **kwargs):
        if not getattr(request, 'organizers', None) and request.scopes != ['profile']:
            raise FatalClientError('No organizers selected.')

        expires = timezone.now() + timedelta(
            seconds=oauth2_settings.AUTHORIZATION_CODE_EXPIRE_SECONDS)
        g = Grant(application=request.client, user=request.user, code=code["code"],
                  expires=expires, redirect_uri=request.redirect_uri,
                  scope=" ".join(request.scopes))
        g.save()
        if request.scopes != ['profile']:
            g.organizers.add(*request.organizers.all())

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        try:
            grant = Grant.objects.get(code=code, application=client)
            if not grant.is_expired():
                request.scopes = grant.scope.split(" ")
                request.user = grant.user
                request.organizers = grant.organizers.all()
                return True
            return False

        except Grant.DoesNotExist:
            return False

    def _create_access_token(self, expires, request, token, source_refresh_token=None):
        if not getattr(request, 'organizers', None) and not getattr(source_refresh_token, 'access_token', None) and token["scope"] != 'profile':
            raise FatalClientError('No organizers selected.')
        if token['scope'] != 'profile':
            if hasattr(request, 'organizers'):
                orgs = list(request.organizers.all())
            else:
                orgs = list(source_refresh_token.access_token.organizers.all())
        access_token = super()._create_access_token(expires, request, token, source_refresh_token=None)
        if token['scope'] != 'profile':
            access_token.organizers.add(*orgs)
        return access_token
