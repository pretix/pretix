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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pypdfium2
import pytest
from django.core.files import File
from django.utils.timezone import now
from django_scopes import scope
from PIL import ImageChops
from pypdf import PdfReader

from pretix.base.models import (
    Event, Item, ItemVariation, Order, OrderPosition, Organizer,
)
from pretix.base.services.export import ExportError
from pretix.plugins.badges.exporters import BadgeExporter


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    with scope(organizer=o):
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(), live=True
        )
        o1 = Order.objects.create(
            code='FOOBAR', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + timedelta(days=10),
            total=Decimal('13.37'),
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        shirt = Item.objects.create(event=event, name='T-Shirt', default_price=12)
        shirt_red = ItemVariation.objects.create(item=shirt, default_price=14, value="Red")
        OrderPosition.objects.create(
            order=o1, item=shirt, variation=shirt_red,
            price=12, attendee_name_parts={}, secret='1234'
        )
        OrderPosition.objects.create(
            order=o1, item=shirt, variation=shirt_red,
            price=12, attendee_name_parts={}, secret='5678'
        )
        yield event, o1, shirt


@pytest.mark.django_db
def test_generate_pdf(env):
    event, order, shirt = env
    event.badge_layouts.create(name="Default", default=True)
    e = BadgeExporter(event, organizer=event.organizer)
    with pytest.raises(ExportError):
        e.render({
            'items': [shirt.pk],
            'rendering': 'one',
            'include_pending': False
        })

    with pytest.raises(ExportError):
        e.render({
            'items': [],
            'rendering': 'one',
            'include_pending': True
        })

    fname, ftype, buf = e.render({
        'items': [shirt.pk],
        'rendering': 'one',
        'include_pending': True
    })
    assert ftype == 'application/pdf'
    pdf = PdfReader(BytesIO(buf))
    assert len(pdf.pages) == 2


@pytest.mark.django_db
def test_generate_pdf_multi(env):
    event, order, shirt = env
    event.badge_layouts.create(name="Default", default=True)
    e = BadgeExporter(event, organizer=event.organizer)
    fname, ftype, buf = e.render({
        'items': [shirt.pk],
        'rendering': 'a4_a6l',
        'include_pending': True
    })
    assert ftype == 'application/pdf'
    pdf = PdfReader(BytesIO(buf))
    assert len(pdf.pages) == 1


def asset_path(name):
    return Path(__file__).parent / "assets" / name


def compare_pdfs(pdf_dir: Path, inp_a: Path | bytes, inp_b: Path | bytes):
    logging.info(f"Comparing pdfs, writing files to {pdf_dir}")

    pdf_a = pypdfium2.PdfDocument(inp_a)
    pdf_b = pypdfium2.PdfDocument(inp_b)

    pdf_a.save(pdf_dir / "a.pdf")
    pdf_b.save(pdf_dir / "b.pdf")

    assert len(pdf_a) == len(pdf_b)

    for i, (page_a, page_b) in enumerate(zip(pdf_a, pdf_b)):
        render_a = page_a.render()
        render_b = page_b.render()
        assert render_a.height == render_b.height
        assert render_a.width == render_b.width

        diff = ImageChops.difference(render_a.to_pil(), render_b.to_pil())
        if diff.getbbox():
            diff.save(pdf_dir / f"{i}.png")
            assert not diff.getbbox(), f"Page {i} differs."


@pytest.mark.django_db
@pytest.mark.parametrize("case", [
    "bg-rotated",
    "bg-mediabox-offset",
    "bg-cropbox"
])
def test_generate_pdf_weird_bgs(pdf_dir, env, case):
    event, order, shirt = env
    asset_folder = asset_path(case)
    with open(asset_folder / "bg.pdf", 'rb') as fi:
        event.badge_layouts.create(name="Default", default=True, background=File(fi, name="test.pdf"))
    e = BadgeExporter(event, organizer=event.organizer)
    fname, ftype, buf = e.render({
        'items': [shirt.pk],
        'rendering': 'one',
        'include_pending': True
    })
    assert ftype == 'application/pdf'
    assert buf

    compare_pdfs(pdf_dir, buf, asset_folder / "expected.pdf")
