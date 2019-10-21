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
        gs = GlobalSettingsObject()
        if not gs.settings.opencagedata_apikey:
            return JsonResponse({
                'success': False,
                'results': []
            }, status=200)

        q = request.GET.get('q')
        cd = cache.get('geocode:{}'.format(q))
        if cd:
            return JsonResponse({
                'success': True,
                'results': cd
            }, status=200)

        try:
            r = requests.get(
                'https://api.opencagedata.com/geocode/v1/json?q={}&key={}'.format(
                    quote(q), gs.settings.opencagedata_apikey
                )
            )
            r.raise_for_status()
        except IOError:
            logger.exception("Geocoding failed")
            return JsonResponse({
                'success': False,
                'results': []
            }, status=200)
        else:
            d = r.json()
        res = [
            {
                'formatted': r['formatted'],
                'lat': r['geometry']['lat'],
                'lon': r['geometry']['lng'],
            } for r in d['results']
        ]
        cache.set('geocode:{}'.format(q), res, timeout=3600 * 6)

        return JsonResponse({
            'success': True,
            'results': res
        }, status=200)
