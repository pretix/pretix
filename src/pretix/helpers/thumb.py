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
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps
from PIL.Image import LANCZOS

from pretix.helpers.models import Thumbnail


class ThumbnailError(Exception):
    pass


def get_sizes(size, imgsize):
    crop = False
    if size.endswith('^'):
        crop = True
        size = size[:-1]

    if 'x' in size:
        size = [int(p) for p in size.split('x')]
    else:
        size = [int(size), int(size)]

    if crop:
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
        if wfactor == hfactor:
            return (int(imgsize[0] * hfactor), int(imgsize[1] * wfactor)), None
        elif wfactor < hfactor:
            return (size[0], int(imgsize[1] * wfactor)), None
        else:
            return (int(imgsize[0] * hfactor), size[1]), None


def create_thumbnail(sourcename, size):
    source = default_storage.open(sourcename)
    image = Image.open(BytesIO(source.read()))
    try:
        image.load()
    except:
        raise ThumbnailError('Could not load image')

    # before we calc thumbnail, we need to check and apply EXIF-orientation
    image = ImageOps.exif_transpose(image)

    scale, crop = get_sizes(size, image.size)
    image = image.resize(scale, resample=LANCZOS)
    if crop:
        image = image.crop(crop)

    checksum = hashlib.md5(image.tobytes()).hexdigest()
    name = checksum + '.' + size.replace('^', 'c') + '.png'
    buffer = BytesIO()
    if image.mode not in ("1", "L", "RGB", "RGBA"):
        image = image.convert('RGB')
    image.save(fp=buffer, format='PNG')
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
