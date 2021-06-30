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
import hashlib
import math
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps
from PIL.Image import LANCZOS

from pretix.helpers.models import Thumbnail


class ThumbnailError(Exception):
    pass

def get_minsize(size):
    if not "_" in size:
        return (0, 0)
    min_width = 0
    min_height = 0
    if "x" in size:
        sizes = size.split('x')
        if sizes[0].endswith("_"):
            min_width = int(sizes[0][:-1])
        if sizes[1].endswith("_"):
            min_height = int(sizes[1][:-1])
    elif size.endswith("_"):
        min_width = int(size[:-1])
        min_height = min_width
    return (min_width, min_height)

def get_sizes(size, imgsize):
    crop = False
    if size.endswith('^'):
        crop = True
        size = size[:-1]

    min_width, min_height = get_minsize(size)
    if min_width or min_height:
        size = size.replace("_", "")

    if 'x' in size:
        size = [int(p) for p in size.split('x')]
    else:
        size = [int(size), int(size)]

    if crop:
        # currently crop and min-size cannot be combined
        wfactor = min(1, size[0] / imgsize[0])
        hfactor = min(1, size[1] / imgsize[1])
        if wfactor == hfactor:
            return (int(imgsize[0] * wfactor), int(imgsize[1] * hfactor)), \
                   (0, int((imgsize[1] * wfactor - imgsize[1] * hfactor) / 2),
                    imgsize[0] * hfactor, int((imgsize[1] * wfactor + imgsize[1] * wfactor) / 2))
        elif wfactor > hfactor:
            return (int(size[0]), int(imgsize[1] * wfactor)), \
                   (0, int((imgsize[1] * wfactor - size[1]) / 2), size[0], int((imgsize[1] * wfactor + size[1]) / 2))
        else:
            return (int(imgsize[0] * hfactor), int(size[1])), \
                   (int((imgsize[0] * hfactor - size[0]) / 2), 0, int((imgsize[0] * hfactor + size[0]) / 2), size[1])
    else:
        wfactor = min(1, size[0] / imgsize[0])
        hfactor = min(1, size[1] / imgsize[1])
        if min_width and min_height:
            wfactor = max(wfactor, hfactor)
        elif min_width:
            wfactor = hfactor
        elif min_height:
            hfactor = wfactor

        if wfactor == hfactor:
            return (int(imgsize[0] * hfactor), int(imgsize[1] * wfactor)), None
        elif wfactor < hfactor:
            return (size[0], int(imgsize[1] * wfactor)), None
        else:
            return (int(imgsize[0] * hfactor), size[1]), None


def resize_image(image, size):
    # before we calc thumbnail, we need to check and apply EXIF-orientation
    image = ImageOps.exif_transpose(image)

    new_size, crop = get_sizes(size, image.size)
    image = image.resize(new_size, resample=LANCZOS)
    if crop:
        image = image.crop(crop)

    min_width, min_height = get_minsize(size)

    if min_width > new_size[0] or min_height > new_size[1]:
        padding = math.ceil(max(min_width - new_size[0], min_height - new_size[1]) / 2)
        image = image.convert('RGB')
        image = ImageOps.expand(image, border=padding, fill="white")

        new_width = max(min_width, new_size[0])
        new_height = max(min_height, new_size[1])
        new_x = (image.width - new_width) // 2
        new_y = (image.height - new_height) // 2

        image = image.crop((new_x, new_y, new_x + new_width, new_y + new_height))

    return image


def create_thumbnail(sourcename, size):
    source = default_storage.open(sourcename)
    image = Image.open(BytesIO(source.read()))
    try:
        image.load()
    except:
        raise ThumbnailError('Could not load image')

    image = resize_image(image, size)

    if source.name.endswith('.jpg') or source.name.endswith('.jpeg'):
        # Yields better file sizes for photos
        target_ext = 'jpeg'
        quality = 95
    else:
        target_ext = 'png'
        quality = None

    checksum = hashlib.md5(image.tobytes()).hexdigest()
    name = checksum + '.' + size.replace('^', 'c') + '.' + target_ext
    buffer = BytesIO()
    if image.mode not in ("1", "L", "RGB", "RGBA"):
        image = image.convert('RGB')
    image.save(fp=buffer, format=target_ext.upper(), quality=quality)
    imgfile = ContentFile(buffer.getvalue())

    t = Thumbnail.objects.create(source=sourcename, size=size)
    t.thumb.save(name, imgfile)
    return t


def get_thumbnail(source, size):
    # Assumes files are immutable
    try:
        return Thumbnail.objects.get(source=source, size=size)
    except Thumbnail.DoesNotExist:
        return create_thumbnail(source, size)
