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
import logging
from io import BytesIO

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL.Image import MAX_IMAGE_PIXELS, DecompressionBombError

IMAGE_TYPES = {'image/gif', 'image/jpeg', 'image/png'}
IMAGE_EXTS = {'.gif', '.jpg', '.jpeg', '.png'}


logger = logging.getLogger(__name__)


def validate_uploaded_file_for_valid_image(f):
    if f is None:
        return None

    from PIL import Image

    # We need to get a file object for Pillow. We might have a path or we might
    # have to read the data into memory.
    if hasattr(f, 'temporary_file_path'):
        file = f.temporary_file_path()
    else:
        if hasattr(f, 'read'):
            file = BytesIO(f.read())
        else:
            file = BytesIO(f['content'])

    try:
        try:
            image = Image.open(file)
            # verify() must be called immediately after the constructor.
            image.verify()
        except DecompressionBombError:
            raise ValidationError(_(
                "The file you uploaded has a very large number of pixels, please upload a picture with smaller dimensions."
            ))

        # load() is a potential DoS vector (see Django bug #18520), so we verify the size first
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValidationError(_(
                "The file you uploaded has a very large number of pixels, please upload a picture with smaller dimensions."
            ))
    except Exception as exc:
        logger.exception('Could not parse image')
        # Pillow doesn't recognize it as an image.
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(_(
            "Upload a valid image. The file you uploaded was either not an image or a corrupted image."
        )) from exc
    if hasattr(f, 'seek') and callable(f.seek):
        f.seek(0)


class ImageSizeValidator:
    def __call__(self, image):
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValidationError(_(
                "The file you uploaded has a very large number of pixels, please upload a picture with smaller dimensions."
            ))
        return image
