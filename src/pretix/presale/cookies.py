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
from enum import Enum
from typing import List

from pretix.presale.signals import register_cookie_providers


class UsageClass(Enum):
    FUNCTIONAL = 1
    ANALYTICS = 2
    MARKETING = 3
    SOCIAL = 4


class CookieProvider:
    def __init__(self, identifier: str, usage_classes: List[UsageClass], provider_name: str, privacy_url: str = None, **kwargs):
        self.identifier = identifier
        self.usage_classes = usage_classes
        self.provider_name = provider_name
        self.privacy_url = privacy_url


def get_cookie_providers(event, request):
    c = [
    ]
    for receiver, response in register_cookie_providers.send(event, request=request):
        if isinstance(response, list):
            c += response
        else:
            c.append(response)
    c.sort(key=lambda k: str(k.provider_name))
    return c
