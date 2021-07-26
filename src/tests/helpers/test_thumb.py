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
from PIL import Image

from pretix.helpers.thumb import resize_image


def test_no_resize():
    img = Image.new('RGB', (40, 20))
    img = resize_image(img, "100x100")
    width, height = img.size
    assert width == 40
    assert height == 20

    img = Image.new('RGB', (40, 20))
    img = resize_image(img, "100x100^")
    width, height = img.size
    assert width == 40
    assert height == 20


def test_resize():
    img = Image.new('RGB', (40, 20))
    img = resize_image(img, "10x10")
    width, height = img.size
    assert width == 10
    assert height == 5

    img = Image.new('RGB', (40, 20))
    img = resize_image(img, "100x10")
    width, height = img.size
    assert width == 20
    assert height == 10

    img = Image.new('RGB', (40, 20))
    img = resize_image(img, "10x100")
    width, height = img.size
    assert width == 10
    assert height == 5


def test_crop():
    img = Image.new('RGB', (40, 20))
    img = resize_image(img, "10x10^")
    width, height = img.size
    assert width == 10
    assert height == 10


def test_exactsize():
    img = Image.new('RGB', (6912, 3456))
    img = resize_image(img, "600_x5000")
    width, height = img.size
    assert width == 600
    assert height == 300

    img = Image.new('RGB', (60, 20))
    img = resize_image(img, "10_x10")
    width, height = img.size
    assert width == 10
    assert height == 3

    img = Image.new('RGB', (10, 20))
    img = resize_image(img, "10_x10")
    width, height = img.size
    assert width == 10
    assert height == 10

    img = Image.new('RGB', (60, 20))
    img = resize_image(img, "10x10_")
    width, height = img.size
    assert width == 10
    assert height == 10

    img = Image.new('RGB', (20, 60))
    img = resize_image(img, "10x10_")
    width, height = img.size
    assert width == 3
    assert height == 10

    img = Image.new('RGB', (20, 60))
    img = resize_image(img, "10_x10_")
    width, height = img.size
    assert width == 10
    assert height == 10

    img = Image.new('RGB', (20, 60))
    img = resize_image(img, "100_x100_")
    width, height = img.size
    assert width == 100
    assert height == 100
