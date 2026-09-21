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
import io
import re

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image

from pretix.helpers.templatetags.thumb import thumbset
from pretix.helpers.thumb import resize_image


def test_no_resize():
    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "100x100")
    width, height = img.size
    assert limited_by_input
    assert width == 40
    assert height == 20

    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "100x100^")
    width, height = img.size
    assert limited_by_input
    assert width == 40
    assert height == 20

    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "40x20^")
    width, height = img.size
    assert not limited_by_input
    assert width == 40
    assert height == 20


def test_resize():
    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "10x10")
    width, height = img.size
    assert not limited_by_input
    assert width == 10
    assert height == 5

    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "100x10")
    width, height = img.size
    assert not limited_by_input
    assert width == 20
    assert height == 10

    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "10x100")
    width, height = img.size
    assert not limited_by_input
    assert width == 10
    assert height == 5


def test_crop():
    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "10x10^")
    width, height = img.size
    assert not limited_by_input
    assert width == 10
    assert height == 10

    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "40x20^")
    width, height = img.size
    assert not limited_by_input
    assert width == 40
    assert height == 20

    img = Image.new('RGB', (40, 20))
    img, limited_by_input = resize_image(img, "50x30^")
    width, height = img.size
    assert limited_by_input
    assert width == 40
    assert height == 20


def test_exactsize():
    img = Image.new('RGB', (6912, 3456))
    img, limited_by_input = resize_image(img, "600_x5000")
    width, height = img.size
    assert not limited_by_input
    assert width == 600
    assert height == 300

    img = Image.new('RGB', (60, 20))
    img, limited_by_input = resize_image(img, "10_x10")
    width, height = img.size
    assert not limited_by_input
    assert width == 10
    assert height == 3

    img = Image.new('RGB', (10, 20))
    img, limited_by_input = resize_image(img, "10_x10")
    width, height = img.size
    assert not limited_by_input
    assert width == 10
    assert height == 10

    img = Image.new('RGB', (60, 20))
    img, limited_by_input = resize_image(img, "10x10_")
    width, height = img.size
    assert not limited_by_input
    assert width == 10
    assert height == 10

    img = Image.new('RGB', (20, 60))
    img, limited_by_input = resize_image(img, "10x10_")
    width, height = img.size
    assert not limited_by_input
    assert width == 3
    assert height == 10

    img = Image.new('RGB', (20, 60))
    img, limited_by_input = resize_image(img, "10_x10_")
    width, height = img.size
    assert not limited_by_input
    assert width == 10
    assert height == 10

    img = Image.new('RGB', (20, 60))
    img, limited_by_input = resize_image(img, "100_x100_")
    width, height = img.size
    assert limited_by_input
    assert width == 100
    assert height == 100

    img = Image.new('RGB', (20, 60))
    img, limited_by_input = resize_image(img, "20_x60_")
    width, height = img.size
    assert not limited_by_input
    assert width == 20
    assert height == 60


def _create_img(size):
    img = Image.new('RGB', size)
    with io.BytesIO() as output:
        img.save(output, format="PNG")
        contents = output.getvalue()
    return default_storage.save("_".join(str(a) for a in size) + ".png", ContentFile(contents))


@pytest.mark.django_db
def test_thumbset():
    # Product picture example
    img = _create_img((60, 60))
    assert not thumbset(img, "60x60^")

    img = _create_img((110, 110))
    assert not thumbset(img, "60x60^")

    img = _create_img((120, 120))
    assert re.match(
        r".*\.120x120c\.png 2x$",
        thumbset(img, "60x60^"),
    )

    img = _create_img((150, 150))
    assert re.match(
        r".*\.120x120c\.png 2x$",
        thumbset(img, "60x60^"),
    )

    img = _create_img((180, 180))
    assert re.match(
        r".*\.120x120c\.png 2x, .*\.180x180c.png 3x$",
        thumbset(img, "60x60^"),
    )

    img = _create_img((500, 500))
    assert re.match(
        r".*\.120x120c\.png 2x, .*\.180x180c.png 3x$",
        thumbset(img, "60x60^"),
    )

    # Event logo (large version) example
    img = _create_img((400, 200))
    assert not thumbset(img, "1170x5000")

    img = _create_img((1170, 120))
    assert not thumbset(img, "1170x5000")

    img = _create_img((2340, 240))
    assert re.match(
        r".*\.2340x10000\.png 2x$",
        thumbset(img, "1170x5000"),
    )

    img = _create_img((2925, 180))
    assert re.match(
        r".*\.2340x10000\.png 2x$",
        thumbset(img, "1170x5000"),
    )

    img = _create_img((3510, 360))
    assert re.match(
        r".*\.2340x10000\.png 2x, .*\.3510x15000.png 3x$",
        thumbset(img, "1170x5000"),
    )

    img = _create_img((4680, 480))
    assert re.match(
        r".*\.2340x10000\.png 2x, .*\.3510x15000.png 3x$",
        thumbset(img, "1170x5000"),
    )
