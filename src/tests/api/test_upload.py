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
import pytest
from django.core.files.base import ContentFile


@pytest.mark.django_db
def test_upload_file(token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'application/pdf',
            'file': ContentFile('file.pdf', 'invalid pdf content')
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
            'file': ContentFile('file.png', 'invalid pdf content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 400
