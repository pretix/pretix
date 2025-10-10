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
from pretix.base.plugins import (
    PLUGIN_LEVEL_EVENT_ORGANIZER_HYBRID, PluginConfig,
)


class TestDummyHybridApp(PluginConfig):
    name = 'tests.testdummyhybrid'
    verbose_name = 'testdummyhybrid'

    class PretixPluginMeta:
        name = 'testdummyhybrid'
        version = '1.0.0'
        level = PLUGIN_LEVEL_EVENT_ORGANIZER_HYBRID
