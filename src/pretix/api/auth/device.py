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
import logging
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError
from django.utils.timezone import now
from django_scopes import scopes_disabled
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from pretix.api.auth.devicesecurity import (
    FullAccessSecurityProfile, get_all_security_profiles,
)
from pretix.base.models import Device
from pretix.base.models.devices import DeviceLastSeen

logger = logging.getLogger(__name__)


class DeviceTokenAuthentication(TokenAuthentication):
    model = Device
    keyword = 'Device'

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            with scopes_disabled():
                device = model.objects.select_related('organizer', 'last_seen').get(api_token=key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')

        if not device.initialized:
            raise exceptions.AuthenticationFailed('Device has not been initialized.')

        if device.revoked:
            logging.warning(f'Connection attempt of revoked device {device.pk}.')
            raise exceptions.AuthenticationFailed('Device access has been revoked.')

        self._update_last_seen(device)
        return AnonymousUser(), device

    def authenticate(self, request):
        r = super().authenticate(request)
        if r and isinstance(r[1], Device):
            profiles = get_all_security_profiles()
            profile = profiles.get(r[1].security_profile, FullAccessSecurityProfile())
            if not profile.is_allowed(request):
                raise exceptions.PermissionDenied('Request denied by device security profile.')
        return r

    def _update_last_seen(self, device: Device):
        try:
            try:
                last_seen_obj = device.last_seen
            except DeviceLastSeen.DoesNotExist:
                # First request from device, create model, ignore result. Use get_or_create to be safe
                # against concurrent create requests
                DeviceLastSeen.objects.get_or_create(device=device, last_seen=now())
            else:
                if now() - last_seen_obj.last_seen < timedelta(seconds=10):
                    # We don't need to know the last seen info of a device to more precision than this,
                    # so we can avoid some database writes if the device is bursting a lot of requests.
                    return
                last_seen_obj.last_seen = now()
                last_seen_obj.save(update_fields=["last_seen"])
        except DatabaseError:
            # Do not stop the request from happening
            logger.exception("Database error while updating last_seen")
