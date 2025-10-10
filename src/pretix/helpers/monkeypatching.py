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
import types
from datetime import datetime
from http import cookies

from PIL import Image
from requests.adapters import HTTPAdapter


def monkeypatch_vobject_performance():
    """
    This works around a performance issue in the unmaintained vobject library which calls
    a very expensive function for every event in a calendar. Since the slow function is
    mostly used to compare timezones to UTC, not to arbitrary other timezones, we can
    add a few early-out optimizations.
    """

    from vobject import icalendar

    old_tzinfo_eq = icalendar.tzinfo_eq
    test_date = datetime(2000, 1, 1)

    def new_tzinfo_eq(tzinfo1, tzinfo2, *args, **kwargs):
        if tzinfo1 is None:
            return tzinfo2 is None
        if tzinfo2 is None:
            return tzinfo1 is None

        n1 = tzinfo1.tzname(test_date)
        n2 = tzinfo2.tzname(test_date)
        if n1 == "UTC" and n2 == "UTC":
            return True
        if n1 == "UTC" or n2 == "UTC":
            return False
        return old_tzinfo_eq(tzinfo1, tzinfo2, *args, **kwargs)

    icalendar.tzinfo_eq = new_tzinfo_eq


def monkeypatch_pillow_safer():
    """
    Pillow supports many file formats, among them EPS. For EPS, Pillow loads GhostScript whenever GhostScript
    is installed (cannot officially be disabled). However, GhostScript is known for regular security vulnerabilities.
    We have no use of reading EPS files and usually prevent this by using `Image.open(…, formats=[…])` to disable EPS
    support explicitly. However, we are worried about our dependencies like reportlab using `Image.open` without the
    `formats=` parameter. Therefore, as a defense in depth approach, we monkeypatch EPS support away by modifying the
    internal image format registry of Pillow.
    """
    if "EPS" in Image.ID:
        Image.ID.remove("EPS")


def monkeypatch_requests_timeout():
    """
    The requests package does not by default set a timeout for outgoing HTTP requests. This is dangerous especially since
    celery tasks have no timeout on the task as a whole (as web requests do), so HTTP requests to a non-responding
    external service could lead to a clogging of the entire celery queue.
    """
    old_httpadapter_send = HTTPAdapter.send

    def httpadapter_send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None, **kwargs):
        if timeout is None:
            timeout = 30
        return types.MethodType(old_httpadapter_send, self)(
            request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies,
            **kwargs
        )

    HTTPAdapter.send = httpadapter_send


def monkeypatch_cookie_morsel():
    # See https://code.djangoproject.com/ticket/34613
    cookies.Morsel._flags.add("partitioned")
    cookies.Morsel._reserved.setdefault("partitioned", "Partitioned")


def monkeypatch_all_at_ready():
    monkeypatch_vobject_performance()
    monkeypatch_pillow_safer()
    monkeypatch_requests_timeout()
    monkeypatch_cookie_morsel()
