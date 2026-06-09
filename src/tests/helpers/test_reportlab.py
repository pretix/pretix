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
from reportlab.platypus import Paragraph


def test_http_access_disabled(monkeypatch):
    def guard(*args, **kwargs):
        pytest.fail("No internet wanted!")

    monkeypatch.setattr('socket.socket', guard)

    with pytest.raises(OSError, match="Cannot open resource"):
        Paragraph(
            '<img src="https://static.pretix.cloud/static/pretixeu/img/opengraph.png"/>',
        )


def test_file_access_disabled_scheme(monkeypatch):
    with pytest.raises(OSError, match="Cannot open resource"):
        Paragraph(
            '<img src="file:///etc/passwd" />',
        )


@pytest.mark.xfail
def test_file_access_disabled_direct(monkeypatch):
    # Unfortunately this is not prevented by the reprotlab config, but the risk is low since only valid images
    # can be used.
    with pytest.raises(OSError, match="Cannot open resource"):
        Paragraph(
            '<img src="/etc/passwd" />',
        )
