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
import sys
import types
from datetime import datetime
from http import cookies

from django.conf import settings
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import (
    ConnectTimeoutError, HTTPError, LocationParseError, NameResolutionError,
    NewConnectionError,
)
from urllib3.util.connection import (
    _TYPE_SOCKET_OPTIONS, _set_socket_options, allowed_gai_family,
)
from urllib3.util.timeout import _DEFAULT_TIMEOUT


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

    def create_connection(
        address: tuple[str, int],
        timeout=_DEFAULT_TIMEOUT,
        source_address: tuple[str, int] | None = None,
        socket_options: _TYPE_SOCKET_OPTIONS | None = None,
    ) -> socket.socket:
        # This is copied from urllib3.util.connection v2.3.0
        host, port = address
        if host.startswith("["):
            host = host.strip("[]")
        err = None

        # Using the value from allowed_gai_family() in the context of getaddrinfo lets
        # us select whether to work with IPv4 DNS records, IPv6 records, or both.
        # The original create_connection function always returns all records.
        family = allowed_gai_family()

        try:
            host.encode("idna")
        except UnicodeError:
            raise LocationParseError(f"'{host}', label empty or too long") from None

        for res in socket.getaddrinfo(host, port, family, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res

            if not getattr(settings, "ALLOW_HTTP_TO_PRIVATE_NETWORKS", False):
                ip_addr = ipaddress.ip_address(sa[0])
                if ip_addr.is_multicast:
                    raise HTTPError(f"Request to multicast address {sa[0]} blocked")
                if ip_addr.is_loopback or ip_addr.is_link_local:
                    raise HTTPError(f"Request to local address {sa[0]} blocked")
                if ip_addr.is_private:
                    raise HTTPError(f"Request to private address {sa[0]} blocked")

            sock = None
            try:
                sock = socket.socket(af, socktype, proto)

                # If provided, set socket level options before connecting.
                _set_socket_options(sock, socket_options)

                if timeout is not _DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)
                if source_address:
                    sock.bind(source_address)
                sock.connect(sa)
                # Break explicitly a reference cycle
                err = None
                return sock

            except OSError as _:
                err = _
                if sock is not None:
                    sock.close()

        if err is not None:
            try:
                raise err
            finally:
                # Break explicitly a reference cycle
                err = None
        else:
            raise OSError("getaddrinfo returns an empty list")

    class ProtectionMixin:
        def _new_conn(self) -> socket.socket:
            # This is 1:1 the version from urllib3.connection.HTTPConnection._new_conn v2.3.0
            # just with a call to our own create_connection
            try:
                sock = create_connection(
                    (self._dns_host, self.port),
                    self.timeout,
                    source_address=self.source_address,
                    socket_options=self.socket_options,
                )
            except socket.gaierror as e:
                raise NameResolutionError(self.host, self, e) from e
            except socket.timeout as e:
                raise ConnectTimeoutError(
                    self,
                    f"Connection to {self.host} timed out. (connect timeout={self.timeout})",
                ) from e

            except OSError as e:
                raise NewConnectionError(
                    self, f"Failed to establish a new connection: {e}"
                ) from e

            sys.audit("http.client.connect", self, self.host, self.port)
            return sock

    class ProtectedHTTPConnection(ProtectionMixin, HTTPConnection):
        pass

    class ProtectedHTTPSConnection(ProtectionMixin, HTTPSConnection):
        pass

    HTTPConnectionPool.ConnectionCls = ProtectedHTTPConnection
    HTTPSConnectionPool.ConnectionCls = ProtectedHTTPSConnection


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
