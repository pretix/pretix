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
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django_scopes import scopes_disabled

from pretix.base.models import Device


@pytest.fixture
def new_device(organizer):
    return Device.objects.create(
        name="Foo",
        all_events=True,
        organizer=organizer
    )


@pytest.mark.django_db
def test_initialize_required_fields(client, new_device: Device):
    resp = client.post('/api/v1/device/initialize')
    assert resp.status_code == 400
    assert resp.data == {
        'token': ['This field is required.'],
        'hardware_brand': ['This field is required.'],
        'hardware_model': ['This field is required.'],
        'software_brand': ['This field is required.'],
        'software_version': ['This field is required.'],
    }


@pytest.mark.django_db
def test_initialize_unknown_token(client, new_device: Device):
    resp = client.post('/api/v1/device/initialize', {
        'token': 'aaa',
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '4.0.0'
    })
    assert resp.status_code == 400
    assert resp.data == {'token': ['Unknown initialization token.']}


@pytest.mark.django_db
def test_initialize_used_token(client, device: Device):
    resp = client.post('/api/v1/device/initialize', {
        'token': device.initialization_token,
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '4.0.0'
    })
    assert resp.status_code == 400
    assert resp.data == {'token': ['This initialization token has already been used.']}


@pytest.mark.django_db
def test_initialize_revoked_token(client, new_device: Device):
    new_device.revoked = True
    new_device.save()
    resp = client.post('/api/v1/device/initialize', {
        'token': new_device.initialization_token,
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '4.0.0'
    })
    assert resp.status_code == 400
    assert resp.data == {'token': ['This initialization token has been revoked.']}


@pytest.mark.django_db
def test_initialize_valid_token(client, new_device: Device):
    resp = client.post('/api/v1/device/initialize', {
        'token': new_device.initialization_token,
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'os_name': 'Android',
        'os_version': '2.3.3',
        'software_version': '4.0.0',
        'rsa_pubkey': '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKagUI8jux+beh\nui'
                      'MoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+WeJND5b+Ja+Ua+AOr4XAvTNWK/ojZ'
                      'DcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVusp2c2BOLIgXXzxKg8oUNeRE8LFzHi45EMVTLOT59L5DK'
                      '\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWrx/fvbNnsrPh8GbOgHWhdXONddQTL\nCudo/VVOdLM9Oe92xJBla+0QeeKgn'
                      'ElBSD55prRNezQjnxGToTist13mOjS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY-----',
    })
    assert resp.status_code == 200
    assert resp.data['organizer'] == 'dummy'
    assert resp.data['name'] == 'Foo'
    assert 'device_id' in resp.data
    assert 'unique_serial' in resp.data
    assert 'api_token' in resp.data
    new_device.refresh_from_db()
    assert new_device.api_token
    assert new_device.initialized
    assert new_device.os_version == "2.3.3"
    assert new_device.rsa_pubkey == '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeG' \
                                    'mKagUI8jux+beh\nuiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83cl' \
                                    'ox\nvS4+WeJND5b+Ja+Ua+AOr4XAvTNWK/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4' \
                                    'bZIp+pRmMAVusp2c2BOLIgXXzxKg8oUNeRE8LFzHi45EMVTLOT59L5DK\nRD1V11/rSpBBl08E5eYe' \
                                    'HEAO8p+WfiS5YVWrx/fvbNnsrPh8GbOgHWhdXONddQTL\nCudo/VVOdLM9Oe92xJBla+0QeeKgnElB' \
                                    'SD55prRNezQjnxGToTist13mOjS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY-----'


@pytest.mark.django_db
def test_update_required_fields(device_client, device: Device):
    resp = device_client.post('/api/v1/device/update')
    assert resp.status_code == 400
    assert resp.data == {
        'hardware_brand': ['This field is required.'],
        'hardware_model': ['This field is required.'],
        'software_brand': ['This field is required.'],
        'software_version': ['This field is required.'],
    }


@pytest.mark.django_db
def test_update_required_auth(client, token_client, device: Device):
    resp = client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0'
    })
    assert resp.status_code == 401
    resp = token_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0'
    })
    assert resp.status_code == 401


@pytest.mark.django_db
def test_update_valid_fields(device_client, device: Device):
    resp = device_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'os_name': 'Android',
        'os_version': '2.3.3',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0',
        'info': {
            'foo': 'bar'
        },
        'rsa_pubkey': '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKagUI8jux+beh\n'
                      'uiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+WeJND5b+Ja+Ua+AOr4XAvTNW'
                      'K/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVusp2c2BOLIgXXzxKg8oUNeRE8LFzHi45EMVTL'
                      'OT59L5DK\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWrx/fvbNnsrPh8GbOgHWhdXONddQTL\nCudo/VVOdLM9Oe92xJ'
                      'Bla+0QeeKgnElBSD55prRNezQjnxGToTist13mOjS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY-----',
    }, format='json')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.software_version == '5.0.0'
    assert device.os_version == '2.3.3'
    assert device.info == {'foo': 'bar'}
    assert device.rsa_pubkey == '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKagU' \
                                'I8jux+beh\nuiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+We' \
                                'JND5b+Ja+Ua+AOr4XAvTNWK/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVusp2' \
                                'c2BOLIgXXzxKg8oUNeRE8LFzHi45EMVTLOT59L5DK\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWrx/fv' \
                                'bNnsrPh8GbOgHWhdXONddQTL\nCudo/VVOdLM9Oe92xJBla+0QeeKgnElBSD55prRNezQjnxGToTist13mO' \
                                'jS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY-----'


@pytest.mark.django_db
def test_update_rsa_unchanged(device_client, device: Device):
    device.rsa_pubkey = '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKagUI8jux+be' \
                        'h\nuiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+WeJND5b+Ja+Ua+AOr4' \
                        'XAvTNWK/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVusp2c2BOLIgXXzxKg8oUNeRE8LFz' \
                        'Hi45EMVTLOT59L5DK\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWrx/fvbNnsrPh8GbOgHWhdXONddQTL\nCudo/V' \
                        'VOdLM9Oe92xJBla+0QeeKgnElBSD55prRNezQjnxGToTist13mOjS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY--' \
                        '---'
    device.save()
    resp = device_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0',
        'info': {
            'foo': 'bar'
        },
        'rsa_pubkey': '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKagUI8jux+beh'
                      '\nuiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+WeJND5b+Ja+Ua+AOr4XA'
                      'vTNWK/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVusp2c2BOLIgXXzxKg8oUNeRE8LFzHi4'
                      '5EMVTLOT59L5DK\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWrx/fvbNnsrPh8GbOgHWhdXONddQTL\nCudo/VVOdL'
                      'M9Oe92xJBla+0QeeKgnElBSD55prRNezQjnxGToTist13mOjS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY-----',
    }, format='json')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.software_version == '5.0.0'
    assert device.info == {'foo': 'bar'}
    assert device.rsa_pubkey == '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKag' \
                                'UI8jux+beh\nuiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+' \
                                'WeJND5b+Ja+Ua+AOr4XAvTNWK/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVu' \
                                'sp2c2BOLIgXXzxKg8oUNeRE8LFzHi45EMVTLOT59L5DK\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWr' \
                                'x/fvbNnsrPh8GbOgHWhdXONddQTL\nCudo/VVOdLM9Oe92xJBla+0QeeKgnElBSD55prRNezQjnxGToTis' \
                                't13mOjS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY-----'


@pytest.mark.django_db
def test_update_rsa_invalid(device_client, device: Device):
    device.save()
    resp = device_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0',
        'info': {
            'foo': 'bar'
        },
        'rsa_pubkey': 'notakey',
    }, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_update_rsa_changed(device_client, device: Device):
    device.rsa_pubkey = '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKagUI8jux+beh' \
                        '\nuiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+WeJND5b+Ja+Ua+AOr4XA' \
                        'vTNWK/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVusp2c2BOLIgXXzxKg8oUNeRE8LFzHi4' \
                        '5EMVTLOT59L5DK\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWrx/fvbNnsrPh8GbOgHWhdXONddQTL\nCudo/VVOdL' \
                        'M9Oe92xJBla+0QeeKgnElBSD55prRNezQjnxGToTist13mOjS4fQ+I\nswIDAQAB\n-----END PUBLIC KEY-----'
    device.save()
    resp = device_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0',
        'info': {
            'foo': 'bar'
        },
        'rsa_pubkey': '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA4ebJ9BfBqZ3Tkndrnbrc\n'
                      '3PPkhbws3U81f3aRMCmZyvzEi/pq1HfsC8fk2YptXDROio2mGt799SZMZBfTwknZ\nNTqkB1ZTVHwO8rz0i1yPphe1I+xN'
                      '/eG8CQiRYCv7nh6+Us989OTgD1sFNx8F9vX/\nAw1TRXUn7F10iPP4J3Ns2j1d4hZyp811Nfgrb0q348qv9TrK52AAQc0F'
                      'UWypAI8K\ngC756SbINSjAJSBvEYqTA2ORIjkoW+xLhbpvaCp5HZ7aARCihxRGmu/H830xf7cL\nK8PEdFCKr8ZDZrRFTi'
                      'bSX8RXIGWhJZBykqBtkNrJniwhq9gcWkGMVP9bQxRnCRzy\nOQIDAQAB\n-----END PUBLIC KEY-----'
    }, format='json')
    assert resp.status_code == 400
    device.refresh_from_db()
    assert device.rsa_pubkey == '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkvaNeGmKagUI' \
                                '8jux+beh\nuiMoH6NUvbhRaY5xg7IMpG2BoauIIRhzwoqNaVHGYPX+7PpYwNxLfvYk2e83clox\nvS4+WeJN' \
                                'D5b+Ja+Ua+AOr4XAvTNWK/ojZDcP3fAjc6pPEVvWPQmq2qLcBjBtkRSv\nH83kAs/4bZIp+pRmMAVusp2c2B' \
                                'OLIgXXzxKg8oUNeRE8LFzHi45EMVTLOT59L5DK\nRD1V11/rSpBBl08E5eYeHEAO8p+WfiS5YVWrx/fvbNns' \
                                'rPh8GbOgHWhdXONddQTL\nCudo/VVOdLM9Oe92xJBla+0QeeKgnElBSD55prRNezQjnxGToTist13mOjS4fQ' \
                                '+I\nswIDAQAB\n-----END PUBLIC KEY-----'


@pytest.mark.django_db
def test_update_valid_without_optional_fields(device_client, device: Device):
    resp = device_client.post('/api/v1/device/update', {
        'hardware_brand': 'Samsung',
        'hardware_model': 'Galaxy S',
        'software_brand': 'pretixdroid',
        'software_version': '5.0.0',
    }, format='json')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.software_version == '5.0.0'


@pytest.mark.django_db
def test_keyroll_required_auth(client, token_client, device: Device):
    resp = client.post('/api/v1/device/roll', {})
    assert resp.status_code == 401
    resp = token_client.post('/api/v1/device/roll', {})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_keyroll_valid(device_client, device: Device):
    token = device.api_token
    resp = device_client.post('/api/v1/device/roll')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.api_token
    assert device.api_token != token


@pytest.mark.django_db
def test_revoke_required_auth(client, token_client, device: Device):
    resp = client.post('/api/v1/device/revoke', {})
    assert resp.status_code == 401
    resp = token_client.post('/api/v1/device/revoke', {})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_revoke_valid(device_client, device: Device):
    resp = device_client.post('/api/v1/device/revoke')
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.revoked


@pytest.mark.django_db
def test_device_info(device_client, device: Device):
    resp = device_client.get('/api/v1/device/info')
    assert resp.status_code == 200
    assert resp.data['device']['organizer'] == 'dummy'
    assert resp.data['device']['name'] == 'Foo'
    assert 'device_id' in resp.data['device']
    assert 'unique_serial' in resp.data['device']
    assert 'api_token' in resp.data['device']
    assert 'pretix' in resp.data['server']['version']


@pytest.mark.django_db
def test_device_info_key_sets(device_client, device: Device):
    device.organizer.settings.reusable_media_type_nfc_mf0aes = True
    resp = device_client.get('/api/v1/device/info')
    assert resp.status_code == 200
    assert resp.data['medium_key_sets'] == []

    device.rsa_pubkey = '-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA4ebJ9BfBqZ3Tkndrnbr' \
                        'c\n3PPkhbws3U81f3aRMCmZyvzEi/pq1HfsC8fk2YptXDROio2mGt799SZMZBfTwknZ\nNTqkB1ZTVHwO8rz0i1yPph' \
                        'e1I+xN/eG8CQiRYCv7nh6+Us989OTgD1sFNx8F9vX/\nAw1TRXUn7F10iPP4J3Ns2j1d4hZyp811Nfgrb0q348qv9Tr' \
                        'K52AAQc0FUWypAI8K\ngC756SbINSjAJSBvEYqTA2ORIjkoW+xLhbpvaCp5HZ7aARCihxRGmu/H830xf7cL\nK8PEdF' \
                        'CKr8ZDZrRFTibSX8RXIGWhJZBykqBtkNrJniwhq9gcWkGMVP9bQxRnCRzy\nOQIDAQAB\n-----END PUBLIC KEY--' \
                        '---'
    device.save()

    resp = device_client.get('/api/v1/device/info')
    assert resp.status_code == 200
    assert len(resp.data['medium_key_sets']) == 1
    ks = resp.data['medium_key_sets'][0]
    with scopes_disabled():
        keyset = device.organizer.medium_key_sets.get(media_type="nfc_mf0aes")

    assert ks['organizer'] == device.organizer.slug
    assert ks['public_id'] == keyset.public_id
    assert ks['active']
    assert ks['media_type'] == 'nfc_mf0aes'
    assert len(keyset.diversification_key) == 16
    assert len(keyset.uid_key) == 16

    private_key = load_pem_private_key(
        b'-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA4ebJ9BfBqZ3Tkndrnbrc3PPkhbws3U81f3aRMCmZyvzEi/pq\n1HfsC8f'
        b'k2YptXDROio2mGt799SZMZBfTwknZNTqkB1ZTVHwO8rz0i1yPphe1I+xN\n/eG8CQiRYCv7nh6+Us989OTgD1sFNx8F9vX/Aw1TRXUn7F1'
        b'0iPP4J3Ns2j1d4hZy\np811Nfgrb0q348qv9TrK52AAQc0FUWypAI8KgC756SbINSjAJSBvEYqTA2ORIjko\nW+xLhbpvaCp5HZ7aARCih'
        b'xRGmu/H830xf7cLK8PEdFCKr8ZDZrRFTibSX8RXIGWh\nJZBykqBtkNrJniwhq9gcWkGMVP9bQxRnCRzyOQIDAQABAoIBAEBLO8pdopBga'
        b'5GB\nrJ7hSrAWOEG523kHbL4A5HS1OmDUDSqb1KDxGr0FoQQrSlHWT05O32pBcj0+L7rD\nL1FaTFhCfuHZt3DRuD1s+xrY9sd6cuMtA8u'
        b'Q3kAh8KJTElOgA2I1TKa0p3KnYLYd\n/cganoBjYAJiREEZHixGZ6fuyZnZGXpkqHuWnc+9LoSSWfqUwKdHMxgwulbQdoai\nCNuKZzSpB'
        b'ikPyNvDYkJVn/eT2OD9qYa+HwPZVojL8yswtTlhPGkmha+LGuBt3JIx\n8tHK6+yAgvrV08Jb9AgmJYrGAxhwK1GWMXr41cFxBs/GXSX+d'
        b'vSbWqpYdUrJ8zhP\nuFn+awMCgYEA9t0WvNcm8PKNQUnUpiuJB9/0vSVITMJhYaN4G/GQ/9eg15LC5qdE\n586fX7SS4UDfwZfruElZIvu'
        b'FhB38/cNoqjEGRERyFuRrmUG5t3974aQGoufCucDP\nFvJgWFlFX8FAvtMRRIu4JGC6ie9dlaReyYPuwRKaJhBEVwcN0lOP10MCgYEA6kM'
        b'Y\nK1mZ3SWBNrhGsNvM3q+4QHq0u2AI5/OkQTjAxy4X6XmPeor4Xrvq5NdcMbCjTUKD\nbyA/JOopxm4eE7kLBMKEBrWivIjn5/TdBl+0J'
        b'HsH1bjfqX/1DD26gFxnxC3Nm9Up\nqcsT9q6zH/lktJsLlGgHc3sNHIIvuXOsX4CgAtMCgYBjrD7K/l/Vt0k7TDEU6s0I\nJe+uEwiPHYi'
        b'uII+VUMLH2esyPyp8cJsMsUt+G+2WD1iI1Osy3EKmMkHlZypH14dB\n+EtccvpRreaX2Ya/xTRilZSsX8EquOOkkzY9VcYB9IhMw/Hb6EH'
        b'wRjHrEX+KtPQk\njyVuRTGCHt1I+isleeHA+wKBgD1Kvrkg4WP+GxexETXW3HxrJ18fe8gGsW3WzmQO\nMEos4i7BEmwyjhdjPWsQedu6Z'
        b'o+hVngtzLeg2LtFNnNcl+hv6FFFFsYTX/HNnEK9\nqYld80fU7hgQFZJVWEWbZ77paQFbvWHic1+4h79W5iVm55m1ujVZva121nvEKxZ1'
        b'\ntefnAoGBAI/vON+iYS9SqQ6G8IZyeut41fRj5nLQgnEUHdfvNn0tKxlXd2DcKPZ/\n20P6xmoNp1QRAWILn0TQ58hLIXHdXqDegdcA/'
        b'W5r4GEbFg28w1lKcm6e07F9PPRz\n/90ZV8BUHZJuCUKL91lGeibs2VtOt4lDZAn3mBrza3udxZ4UwzRT\n'
        b'-----END RSA PRIVATE KEY-----',
        None
    )
    assert bytes(keyset.uid_key) == private_key.decrypt(
        base64.b64decode(ks['uid_key']),
        padding.PKCS1v15()
    )
    assert bytes(keyset.diversification_key) == private_key.decrypt(
        base64.b64decode(ks['diversification_key']),
        padding.PKCS1v15()
    )
