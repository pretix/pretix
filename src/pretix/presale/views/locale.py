#
# This file is part of pretix Community.
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
# ADDITIONAL TERMS: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are applicable
# granting you additional permissions and placing additional restrictions on your usage of this software. Please refer
# to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive this file, see
# <https://pretix.eu/about/en/license>.
#
from datetime import datetime, timedelta

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import View

from pretix.helpers.cookies import set_cookie_without_samesite

from .robots import NoSearchIndexViewMixin


class LocaleSet(NoSearchIndexViewMixin, View):

    def get(self, request, *args, **kwargs):
        url = request.GET.get('next', request.headers.get('Referer', '/'))
        url = url if url_has_allowed_host_and_scheme(url, allowed_hosts=[request.get_host()]) else '/'
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
