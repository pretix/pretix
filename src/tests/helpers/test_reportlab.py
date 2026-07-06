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
import pytest
from django.core.exceptions import SuspiciousFileOperation
from reportlab.platypus import Paragraph


def test_http_access_disabled(monkeypatch):
    def guard(*args, **kwargs):
        pytest.fail("No internet wanted!")

    monkeypatch.setattr('socket.socket', guard)

    with pytest.raises(SuspiciousFileOperation, match="should not be reading images from disk"):
        Paragraph(
            '<img src="https://static.pretix.cloud/static/pretixeu/img/opengraph.png"/>',
        )


def test_file_access_disabled_scheme(monkeypatch):
    with pytest.raises(SuspiciousFileOperation, match="should not be reading images from disk"):
        Paragraph(
            '<img src="file:///etc/passwd" />',
        )


def test_file_access_disabled_direct(monkeypatch):
    with pytest.raises(SuspiciousFileOperation, match="should not be reading images from disk"):
        Paragraph(
            '<img src="/etc/passwd" />',
        )
