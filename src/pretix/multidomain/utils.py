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
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.templatetags.static import static

from pretix.base.models import Event
from pretix.multidomain.urlreverse import (
    get_event_domain, get_organizer_domain,
)


def static_absolute(object, path):
    sp = static(path)
    if sp.startswith("/"):
        if isinstance(object, Event):
            domain = get_event_domain(object, fallback=True)
        else:
            domain = get_organizer_domain(object)
        if domain:
            siteurlsplit = urlsplit(settings.SITE_URL)
            if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                domain = '%s:%d' % (domain, siteurlsplit.port)
            sp = urljoin('%s://%s' % (siteurlsplit.scheme, domain), sp)
        else:
            sp = urljoin(settings.SITE_URL, sp)
    return sp
