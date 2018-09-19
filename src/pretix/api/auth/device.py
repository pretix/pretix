from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from pretix.base.models import Device


class DeviceTokenAuthentication(TokenAuthentication):
    model = Device
    keyword = 'Device'

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            device = model.objects.select_related('organizer').get(api_token=key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')

        if not device.initialized:
            raise exceptions.AuthenticationFailed('Device has not been initialized.')

        if not device.api_token:
            raise exceptions.AuthenticationFailed('Device access has been revoked.')

        return AnonymousUser(), device
