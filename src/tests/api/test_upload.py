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
