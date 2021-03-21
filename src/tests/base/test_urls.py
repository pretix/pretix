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
# This file contains Apache-licensed contributions copyrighted by: Tim Freund
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from importlib import import_module

from django.conf import settings
from django.test import TestCase


class URLTestCase(TestCase):
    """
    This test case tests for a name string on all URLs.  Unnamed
    URLs will cause a TypeError in the metrics middleware.
    """
    pattern_attrs = ['urlpatterns', 'url_patterns']

    def test_url_names(self):
        urlconf = import_module(settings.ROOT_URLCONF)
        nameless = self.find_nameless_urls(urlconf)
        message = "URL regexes missing names: %s" % " ".join([n.regex.pattern for n in nameless])
        self.assertIs(len(nameless), 0, message)

    def find_nameless_urls(self, conf):
        nameless = []
        patterns = self.get_patterns(conf)
        for u in patterns:
            if self.has_patterns(u):
                nameless.extend(self.find_nameless_urls(u))
            else:
                if u.name is None:
                    nameless.append(u)
        return nameless

    def get_patterns(self, conf):
        for pa in self.pattern_attrs:
            if hasattr(conf, pa):
                return getattr(conf, pa)
        return []

    def has_patterns(self, conf):
        for pa in self.pattern_attrs:
            if hasattr(conf, pa):
                return True
        return False
