from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from pretix.base.models.organizer import TeamAPIToken


class TeamTokenAuthentication(TokenAuthentication):
    model = TeamAPIToken

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            token = model.objects.select_related('team', 'team__organizer').get(token=key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')

        if not token.active:
            raise exceptions.AuthenticationFailed('Token inactive or deleted.')

        return AnonymousUser(), token
