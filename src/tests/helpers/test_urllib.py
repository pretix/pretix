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
from socket import AF_INET, SOCK_STREAM
from unittest import mock

import pytest
import requests
from django.test import override_settings
from dns.inet import AF_INET6
from urllib3.exceptions import HTTPError


def test_local_blocked():
    with pytest.raises(HTTPError, match="Request to local address.*"):
        requests.get("http://localhost", timeout=0.1)
    with pytest.raises(HTTPError, match="Request to local address.*"):
        requests.get("https://localhost", timeout=0.1)


def test_private_ip_blocked():
    with pytest.raises(HTTPError, match="Request to private address.*"):
        requests.get("http://10.0.0.1", timeout=0.1)
    with pytest.raises(HTTPError, match="Request to private address.*"):
        requests.get("https://10.0.0.1", timeout=0.1)


@pytest.mark.django_db
@pytest.mark.parametrize("res", [
    [(AF_INET, SOCK_STREAM, 6, '', ('10.0.0.3', 443))],
    [(AF_INET, SOCK_STREAM, 6, '', ('0.0.0.0', 443))],
    [(AF_INET, SOCK_STREAM, 6, '', ('127.1.1.1', 443))],
    [(AF_INET, SOCK_STREAM, 6, '', ('192.168.5.3', 443))],
    [(AF_INET, SOCK_STREAM, 6, '', ('224.0.0.1', 443))],
    [(AF_INET6, SOCK_STREAM, 6, '', ('::1', 443, 0, 0))],
    [(AF_INET6, SOCK_STREAM, 6, '', ('fe80::1', 443, 0, 0))],
    [(AF_INET6, SOCK_STREAM, 6, '', ('ff00::1', 443, 0, 0))],
    [(AF_INET6, SOCK_STREAM, 6, '', ('fc00::1', 443, 0, 0))],
])
def test_dns_resolving_to_local_blocked(res):
    with mock.patch('socket.getaddrinfo') as mock_addr:
        mock_addr.return_value = res
        with pytest.raises(HTTPError, match="Request to (multicast|private|local) address.*"):
            requests.get("https://example.org", timeout=0.1)
        with pytest.raises(HTTPError, match="Request to (multicast|private|local) address.*"):
            requests.get("http://example.org", timeout=0.1)


def test_dns_remote_allowed():
    class SocketOk(Exception):
        pass

    def side_effect(*args, **kwargs):
        raise SocketOk

    with mock.patch('socket.getaddrinfo') as mock_addr, mock.patch('socket.socket') as mock_socket:
        mock_addr.return_value = [(AF_INET, SOCK_STREAM, 6, '', ('8.8.8.8', 443))]
        mock_socket.side_effect = side_effect
        with pytest.raises(SocketOk):
            requests.get("https://example.org", timeout=0.1)


@override_settings(ALLOW_HTTP_TO_PRIVATE_NETWORKS=True)
def test_local_is_allowed():
    class SocketOk(Exception):
        pass

    def side_effect(*args, **kwargs):
        raise SocketOk

    with mock.patch('socket.getaddrinfo') as mock_addr, mock.patch('socket.socket') as mock_socket:
        mock_addr.return_value = [(AF_INET, SOCK_STREAM, 6, '', ('10.0.0.1', 443))]
        mock_socket.side_effect = side_effect
        with pytest.raises(SocketOk):
            requests.get("https://example.org", timeout=0.1)
