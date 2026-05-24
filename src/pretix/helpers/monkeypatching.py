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
import ipaddress
import socket
import types
from datetime import datetime
from http import cookies

from django.conf import settings
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3 import poolmanager
from urllib3.contrib.resolver.system import SystemResolver
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import HTTPError


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


class ProtectedSystemResolver(SystemResolver):
    def getaddrinfo(
        self,
        host: bytes | str | None,
        port: str | int | None,
        family: socket.AddressFamily,
        type: socket.SocketKind,
        proto: int = 0,
        flags: int = 0,
        *,
        quic_upgrade_via_dns_rr: bool = False,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str | bytes,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        addrs = super().getaddrinfo(host, port, family, type, proto, flags, quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr)
        if not getattr(settings, "ALLOW_HTTP_TO_PRIVATE_NETWORKS", False):
            for addr in addrs:
                addr = addr[4][0]
                ip_addr = ipaddress.ip_address(addr)
                if ip_addr.is_multicast:
                    raise HTTPError(f"Request to multicast address {addr} blocked")
                if ip_addr.is_loopback or ip_addr.is_link_local:
                    raise HTTPError(f"Request to local address {addr} blocked")
                if ip_addr.is_private:
                    raise HTTPError(f"Request to private address {addr} blocked")
        return addrs


def monkeypatch_urllib3_ssrf_protection():
    """
    pretix allows HTTP requests to untrusted URLs, e.g. through webhooks or external API URLs. This is dangerous since
    it can allow access to private networks that should not be reachable by users ("server-side request forgery", SSRF).
    Validating URLs at submission is not sufficient, since with DNS rebinding an attacker can make a domain name pass
    validation and then resolve to a private IP address on actual execution. Unfortunately, there seems no clean solution
    to this in Python land, so we monkeypatch urllib3's connection management to check the IP address to be external
    *after* the DNS resolution.

    This does not work when a global http(s) proxy is used, but in that scenario the proxy can perform the validation.
    """
    if getattr(settings, "ALLOW_HTTP_TO_PRIVATE_NETWORKS", False):
        # Settings are not supposed to change during runtime, so we can optimize performance and complexity by skipping
        # this if not needed.
        return

    class ProtectedHTTPConnectionPool(HTTPConnectionPool):
        def __init__(self, *args, **kwargs):
            kwargs.update({
                "resolver": ProtectedSystemResolver()
            })
            super().__init__(*args, **kwargs)

    class ProtectedHTTPSConnectionPool(HTTPSConnectionPool):
        def __init__(self, *args, **kwargs):
            kwargs.update({
                "resolver": ProtectedSystemResolver()
            })
            super().__init__(*args, **kwargs)

    poolmanager.pool_classes_by_scheme['http'] = ProtectedHTTPConnectionPool
    poolmanager.pool_classes_by_scheme['https'] = ProtectedHTTPSConnectionPool


def monkeypatch_cookie_morsel():
    # See https://code.djangoproject.com/ticket/34613
    cookies.Morsel._flags.add("partitioned")
    cookies.Morsel._reserved.setdefault("partitioned", "Partitioned")


def monkeypatch_all_at_ready():
    monkeypatch_vobject_performance()
    monkeypatch_pillow_safer()
    monkeypatch_requests_timeout()
    monkeypatch_urllib3_ssrf_protection()
    monkeypatch_cookie_morsel()
