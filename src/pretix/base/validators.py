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
import calendar

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule, rrulestr
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Christopher Dambamuromo, Sohalt
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.


class BanlistValidator:
    banlist = []

    def __call__(self, value):
        # Validation logic
        if value in self.banlist:
            raise ValidationError(
                _('This field has an invalid value: %(value)s.'),
                code='invalid',
                params={'value': value},
            )


@deconstructible
class EventSlugBanlistValidator(BanlistValidator):
    banlist = [
        'download',
        'healthcheck',
        'locale',
        'control',
        'redirect',
        'jsi18n',
        'metrics',
        '_global',
        '__debug__',
        'api',
        'events',
        'csp_report',
        'widget',
        'customer',
        'account',
        'lead',
        'accessibility',
    ]


@deconstructible
class OrganizerSlugBanlistValidator(BanlistValidator):
    banlist = [
        'download',
        'healthcheck',
        'locale',
        'control',
        'pretixdroid',
        'redirect',
        'jsi18n',
        'metrics',
        '_global',
        '__debug__',
        'about',
        'api',
        'csp_report',
        'widget',
        'lead',
        'scheduling',
    ]


@deconstructible
class EmailBanlistValidator(BanlistValidator):
    banlist = [
        settings.PRETIX_EMAIL_NONE_VALUE,
    ]


def multimail_validate(val):
    s = val.split(',')
    for part in s:
        validate_email(part.strip())
    return s


class RRuleValidator:
    def __init__(self, enforce_simple=False):
        self.enforce_simple = enforce_simple

    def __call__(self, value):
        try:
            parsed = rrulestr(value)
        except Exception:
            raise ValidationError("Not a valid rrule.")

        if self.enforce_simple:
            # Validate that only things are used that we can represent in our UI for later editing

            if not isinstance(parsed, rrule):
                raise ValidationError("Only a single RRULE is allowed, no combination of rules.")

            if parsed._freq not in (YEARLY, MONTHLY, WEEKLY, DAILY):
                raise ValidationError("Unsupported FREQ value")
            if parsed._wkst != calendar.firstweekday():
                raise ValidationError("Unsupported WKST value")
            if parsed._bysetpos:
                if len(parsed._bysetpos) > 1:
                    raise ValidationError("Only one BYSETPOS value allowed")
                if parsed._freq == YEARLY and parsed._bysetpos not in (1, 2, 3, -1):
                    raise ValidationError("BYSETPOS value not allowed, should be 1, 2, 3 or -1")
                elif parsed._freq == MONTHLY and parsed._bysetpos not in (1, 2, 3, -1):
                    raise ValidationError("BYSETPOS value not allowed, should be 1, 2, 3 or -1")
                elif parsed._freq not in (YEARLY, MONTHLY):
                    raise ValidationError("BYSETPOS not allowed for this FREQ")
            if parsed._bymonthday:
                raise ValidationError("BYMONTHDAY not supported")
            if parsed._byyearday:
                raise ValidationError("BYYEARDAY not supported")
            if parsed._byeaster:
                raise ValidationError("BYEASTER not supported")
            if parsed._byweekno:
                raise ValidationError("BYWEEKNO not supported")
            if len(parsed._byhour) > 1 or set(parsed._byhour) != {parsed._dtstart.hour}:
                raise ValidationError("BYHOUR not supported")
            if len(parsed._byminute) > 1 or set(parsed._byminute) != {parsed._dtstart.minute}:
                raise ValidationError("BYMINUTE not supported")
            if len(parsed._bysecond) > 1 or set(parsed._bysecond) != {parsed._dtstart.second}:
                raise ValidationError("BYSECOND not supported")
