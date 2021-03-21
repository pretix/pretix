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
from django.contrib.auth.models import AnonymousUser
from django_scopes import scopes_disabled
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from pretix.api.auth.devicesecurity import (
    DEVICE_SECURITY_PROFILES, FullAccessSecurityProfile,
)
from pretix.base.models import Device


class DeviceTokenAuthentication(TokenAuthentication):
    model = Device
    keyword = 'Device'

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            with scopes_disabled():
                device = model.objects.select_related('organizer').get(api_token=key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')

        if not device.initialized:
            raise exceptions.AuthenticationFailed('Device has not been initialized.')

        if device.revoked:
            raise exceptions.AuthenticationFailed('Device access has been revoked.')

        return AnonymousUser(), device

    def authenticate(self, request):
        r = super().authenticate(request)
        if r and isinstance(r[1], Device):
            profile = DEVICE_SECURITY_PROFILES.get(r[1].security_profile, FullAccessSecurityProfile)
            if not profile.is_allowed(request):
                raise exceptions.PermissionDenied('Request denied by device security profile.')
        return r
