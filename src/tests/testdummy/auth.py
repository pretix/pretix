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

from django import forms

from pretix.base.auth import BaseAuthBackend
from pretix.base.models import User


class TestFormAuthBackend(BaseAuthBackend):
    identifier = 'test_form'
    verbose_name = 'Form'

    @property
    def login_form_fields(self) -> dict:
        return OrderedDict([
            ('username', forms.CharField(max_length=100)),
            ('password', forms.CharField(max_length=100)),
        ])

    def form_authenticate(self, request, form_data):
        if form_data['username'] == 'foo' and form_data['password'] == 'bar':
            return User.objects.get_or_create(
                email='foo@example.com',
                auth_backend='test_form'
            )[0]


class TestRequestAuthBackend(BaseAuthBackend):
    identifier = 'test_request'
    verbose_name = 'Request'
    visible = False

    def request_authenticate(self, request):
        if 'X-Login-Email' in request.headers:
            return User.objects.get_or_create(
                email=request.headers['X-Login-Email'],
                auth_backend='test_request'
            )[0]

    def get_next_url(self, request):
        if 'state' in request.GET:
            return request.GET.get('state')
        return None
