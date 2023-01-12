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
import io
import math

import pytest
from django.core.files.base import ContentFile
from PIL import Image
from PIL.Image import MAX_IMAGE_PIXELS
from tests.const import SAMPLE_PNG


@pytest.mark.django_db
def test_upload_file(token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'application/pdf',
            'file': ContentFile('invalid pdf content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.pdf"',
    )
    assert r.status_code == 201
    assert r.data['id'].startswith('file:')


@pytest.mark.django_db
def test_upload_file_extension_mismatch(token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'application/pdf',
            'file': ContentFile('invalid pdf content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 400
    assert r.data == ['File name "file.png" has an invalid extension for type "application/pdf"']


@pytest.mark.django_db
def test_upload_file_extension_not_allowed(token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'application/octet-stream',
            'file': ContentFile('invalid pdf content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.bin"',
    )
    assert r.status_code == 400
    assert r.data == ['Content type "application/octet-stream" is not allowed']


@pytest.mark.django_db
def test_upload_invalid_image(token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'image/png',
            'file': ContentFile('invalid png content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 400
    assert r.data == ['Upload a valid image. The file you uploaded was either not an image or a corrupted image.']


@pytest.mark.django_db
def test_upload_valid_image(token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'image/png',
            'file': ContentFile(SAMPLE_PNG)
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 201


@pytest.mark.django_db
@pytest.mark.filterwarnings("ignore")
def test_upload_image_with_invalid_dimensions(token_client):
    d = int(math.sqrt(MAX_IMAGE_PIXELS)) + 100
    img = Image.new('RGB', (d, d), color='red')
    output = io.BytesIO()
    img.save(output, format='PNG')
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'image/png',
            'file': ContentFile(output.getvalue())
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 400
    assert r.data == ['The file you uploaded has a very large number of pixels, please upload a picture with smaller dimensions.']
