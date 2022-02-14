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
# This file contains Apache-licensed contributions copyrighted by: Maico Timmerman
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import OrderedDict
from importlib import import_module

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _


def get_auth_backends():
    backends = {}
    for b in settings.PRETIX_AUTH_BACKENDS:
        mod, name = b.rsplit('.', 1)
        b = getattr(import_module(mod), name)()
        backends[b.identifier] = b
    return backends


class BaseAuthBackend:
    """
    This base class defines the interface that needs to be implemented by every class that supplies
    an authentication method to pretix. Please note that pretix authentication backends are different
    from plain Django authentication backends! Be sure to read the documentation chapter on authentication
    backends before you implement one.
    """

    @property
    def identifier(self):
        """
        A short and unique identifier for this authentication backend.
        This should only contain lowercase letters and in most cases will
        be the same as your package name.
        """
        raise NotImplementedError()

    @property
    def verbose_name(self):
        """
        A human-readable name of this authentication backend.
        """
        raise NotImplementedError()

    @property
    def visible(self):
        """
        Whether or not this backend can be selected by users actively. Set this to ``False``
        if you only implement ``request_authenticate``.
        """
        return True

    @property
    def login_form_fields(self) -> dict:
        """
        This property may return form fields that the user needs to fill in to log in.
        """
        return {}

    def form_authenticate(self, request, form_data):
        """
        This method will be called after the user filled in the login form. ``request`` will contain
        the current request and ``form_data`` the input for the form fields defined in ``login_form_fields``.
        You are expected to either return a ``User`` object (if login was successful) or ``None``.

        You are expected to either return a ``User`` object (if login was successful) or ``None``. You should
        obtain this user object using ``User.objects.get_or_create_for_backend``.
        """
        return

    def request_authenticate(self, request):
        """
        This method will be called when the user opens the login form. If the user already has a valid session
        according to your login mechanism, for example a cookie set by a different system or HTTP header set by a
        reverse proxy, you can directly return a ``User`` object that will be logged in.

        ``request`` will contain the current request.

        You are expected to either return a ``User`` object (if login was successful) or ``None``. You should
        obtain this user object using ``User.objects.get_or_create_for_backend``.
        """
        return

    def authentication_url(self, request):
        """
        This method will be called to populate the URL for your authentication method's tab on the login page.
        For example, if your method works through OAuth, you could return the URL of the OAuth authorization URL the
        user needs to visit.

        If you return ``None`` (the default), the link will point to a page that shows the form defined by
        ``login_form_fields``.
        """
        return

    def get_next_url(self, request):
        """
        This method will be called after a successful login to determine the next URL. Pretix in general uses the
        ``'next'`` query parameter. However, external authentication methods could use custom attributes with hardcoded
        names for security purposes. For example, OAuth uses ``'state'`` for keeping track of application state.
        """
        if "next" in request.GET:
            return request.GET.get("next")
        return None


class NativeAuthBackend(BaseAuthBackend):
    identifier = 'native'

    @property
    def verbose_name(self):
        return _('{system} User').format(system=settings.PRETIX_INSTANCE_NAME)

    @property
    def login_form_fields(self) -> dict:
        """
        This property may return form fields that the user needs to fill in
        to log in.
        """
        d = OrderedDict([
            ('email', forms.EmailField(label=_("E-mail"), max_length=254,
                                       widget=forms.EmailInput(attrs={'autofocus': 'autofocus'}))),
            ('password', forms.CharField(label=_("Password"), widget=forms.PasswordInput,
                                         max_length=4096)),
        ])
        return d

    def form_authenticate(self, request, form_data):
        u = authenticate(request=request, email=form_data['email'].lower(), password=form_data['password'])
        if u and u.auth_backend == self.identifier:
            return u
