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

# Date according to https://docs.djangoproject.com/en/dev/ref/templates/builtins/#date

# Django's fr_CA locale leaves the "h" in its time formats unescaped, so it is interpreted as the
# 12-hour-clock hour instead of a literal "h". At midnight this renders a time like "00 h 20" as
# "00 12 20" (see GitHub issue #6117). This was fixed upstream in Django 6.0 (commit b67a36ec) but
# was not backported to the 5.2 series we depend on, so we override the affected formats here.
# This file can be removed once we require Django >= 6.0.
#
# \xa0 is the non-breaking space Django uses in the fr_CA time formats.
TIME_FORMAT = "H\xa0\\h\xa0i"
DATETIME_FORMAT = "j F Y, H\xa0\\h\xa0i"
SHORT_DATETIME_FORMAT = "Y-m-d H\xa0\\h\xa0i"
