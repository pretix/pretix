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
from PIL import Image, ImageOps, ImageSequence
from PIL.Image import Resampling

from pretix.helpers.models import Thumbnail


class ThumbnailError(Exception):
    pass


"""

# How "size" works:


## normal resize

image|thumb:"100x100" resizes the image proportionally to a maximum width and maximum height of 100px.
I.e. an image of 200x100 will be resized to 100x50.
An image of 40x80 will stay 40x80.


## cropped resize with ^

image|thumb:"100x100^" resizes the image proportionally to a minimum width and minimum height of 100px and then will be cropped to 100x100.
I.e. an image of 300x200 will be resized to 150x100 and then cropped from center to 100x100.
An image of 40x80 will stay 40x80.


## exact-size resize with _

exact-size-operator "_" works for width and height independently, so the following is possible:

image|thumb:"100_x100" resizes the image to a maximum height of 100px (if it is lower, it does not upscale) and makes it exactly 100px wide
(if the resized image would be less than 100px wide it adds a white background to both sides to make it at least 100px wide).
I.e. an image of 300x200 will be resized to 150x100.
An image of 40x80 will stay 40x80 but padded with a white background to be 100x80.

image|thumb:"100x100_" resizes the image to a maximum width of 100px (if it is lower, it does not upscale) and makes it at least 100px high
(if the resized image would be less than 100px high it adds a white background to top and bottom to make it at least 100px high).
I.e. an image of 400x200 will be resized to 100x50 and then padded from center to be 100x100.
An image of 40x80 will stay 40x80 but padded with a white background to be 40x100.

image|thumb:"100_x100_" resizes the image proportionally to either a width or height of 100px – it takes the smaller side and resizes that to 100px,
so the longer side will at least be 100px. So the resulting image will at least be 100px wide and at least 100px high. If the original image is bigger
than 100x100 then no padding will occur. If the original image is smaller than 100x100, no resize will happen but padding to 100x100 will occur.
I.e. an image of 400x200 will be resized to 200x100.
An image of 40x80 will stay 40x80 but padded with a white background to be 100x100.

"""


def get_minsize(size):
    if "_" not in size:
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

    if crop and "_" in size:
        raise ThumbnailError('Size %s has errors: crop and minsize cannot be combined.' % size)

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
    image = image.resize(new_size, resample=Resampling.LANCZOS)
    if crop:
        image = image.crop(crop)

    min_width, min_height = get_minsize(size)

    if min_width > new_size[0] or min_height > new_size[1]:
        padding = math.ceil(max(min_width - new_size[0], min_height - new_size[1]) / 2)
        if image.mode not in ("RGB", "RGBA"):
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

    frames = [resize_image(frame, size) for frame in ImageSequence.Iterator(image)]
    image_out = frames[0]
    save_kwargs = {}

    if source.name.lower().endswith('.jpg') or source.name.lower().endswith('.jpeg'):
        # Yields better file sizes for photos
        target_ext = 'jpeg'
        quality = 95
    elif source.name.lower().endswith('.gif') or source.name.lower().endswith('.png'):
        target_ext = source.name.lower()[-3:]
        quality = None
        image_out.info = image.info
        save_kwargs = {
            'append_images': frames[1:],
            'loop': image.info.get('loop', 0),
            'save_all': True,
        }
    else:
        target_ext = 'png'
        quality = None

    checksum = hashlib.md5(image.tobytes()).hexdigest()
    name = checksum + '.' + size.replace('^', 'c') + '.' + target_ext
    buffer = BytesIO()
    if image_out.mode == "P" and source.name.lower().endswith('.png'):
        image_out = image_out.convert('RGBA')
    if image_out.mode not in ("1", "L", "RGB", "RGBA"):
        image_out = image_out.convert('RGB')
    image_out.save(fp=buffer, format=target_ext.upper(), quality=quality, **save_kwargs)
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
