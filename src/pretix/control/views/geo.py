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
from urllib.parse import quote

import requests
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import JsonResponse
from django.views.generic.base import View

from pretix.base.settings import GlobalSettingsObject

logger = logging.getLogger(__name__)


class GeoCodeView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        q = self.request.GET.get('q')
        cd = cache.get('geocode:{}'.format(q))
        if cd:
            return JsonResponse({
                'success': True,
                'results': cd
            }, status=200)

        gs = GlobalSettingsObject()
        try:
            if gs.settings.opencagedata_apikey:
                res = self._use_opencage(q)
            elif gs.settings.mapquest_apikey:
                res = self._use_mapquest(q)
            else:
                return JsonResponse({
                    'success': False,
                    'results': []
                }, status=200)
        except IOError:
            logger.exception("Geocoding failed")
            return JsonResponse({
                'success': False,
                'results': []
            }, status=200)

        cache.set('geocode:{}'.format(q), res, timeout=3600 * 6)
        return JsonResponse({
            'success': True,
            'results': res
        }, status=200)

    def _use_opencage(self, q):
        gs = GlobalSettingsObject()

        r = requests.get(
            'https://api.opencagedata.com/geocode/v1/json?q={}&key={}'.format(
                quote(q), gs.settings.opencagedata_apikey
            )
        )
        r.raise_for_status()
        d = r.json()
        res = [
            {
                'formatted': r['formatted'],
                'lat': r['geometry']['lat'],
                'lon': r['geometry']['lng'],
            } for r in d['results']
        ]
        return res

    def _use_mapquest(self, q):
        gs = GlobalSettingsObject()

        r = requests.get(
            'https://www.mapquestapi.com/geocoding/v1/address?location={}&key={}'.format(
                quote(q), gs.settings.mapquest_apikey
            )
        )
        r.raise_for_status()
        d = r.json()
        res = [
            {
                'formatted': q,
                'lat': r['locations'][0]['latLng']['lat'],
                'lon': r['locations'][0]['latLng']['lng'],
            } for r in d['results']
        ]
        return res
