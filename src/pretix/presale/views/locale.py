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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

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
