from datetime import datetime, timedelta

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import is_safe_url
from django.views.generic import View

from pretix.helpers.cookies import set_cookie_without_samesite

from .robots import NoSearchIndexViewMixin


class LocaleSet(NoSearchIndexViewMixin, View):

    def get(self, request, *args, **kwargs):
        url = request.GET.get('next', request.headers.get('Referer', '/'))
        url = url if is_safe_url(url, allowed_hosts=[request.get_host()]) else '/'
        resp = HttpResponseRedirect(url)

        locale = request.GET.get('locale')
        if locale in [lc for lc, ll in settings.LANGUAGES]:

            max_age = 10 * 365 * 24 * 60 * 60
            set_cookie_without_samesite(
                request, resp,
                settings.LANGUAGE_COOKIE_NAME,
                locale,
                max_age=max_age,
                expires=(datetime.utcnow() + timedelta(seconds=max_age)).strftime(
                    '%a, %d-%b-%Y %H:%M:%S GMT'),
                domain=settings.SESSION_COOKIE_DOMAIN
            )

        return resp
