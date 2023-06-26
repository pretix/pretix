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
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Device


@pytest.fixture
def device(organizer, event):
    t = organizer.devices.create(
        device_id=1,
        name='Scanner',
        hardware_brand="Zebra",
        unique_serial="UOS3GNZ27O39V3QS",
        initialization_token="frkso3m2w58zuw70",
        hardware_model="TC25",
        os_name="Android",
        os_version="8.1.0",
        software_brand="pretixSCAN",
        software_version="1.5.1",
        initialized=now(),
        all_events=False,
    )
    t.limit_events.add(event)
    return t


TEST_DEV_RES = {
    "device_id": 1,
    "unique_serial": "UOS3GNZ27O39V3QS",
    "initialization_token": "frkso3m2w58zuw70",
    "all_events": False,
    "limit_events": [
        "dummy"
    ],
    "revoked": False,
    "name": "Scanner",
    "created": "2020-09-18T14:17:40.971519Z",
    "initialized": "2020-09-18T14:17:44.190021Z",
    "hardware_brand": "Zebra",
    "hardware_model": "TC25",
    "os_name": "Android",
    "os_version": "8.1.0",
    "software_brand": "pretixSCAN",
    "software_version": "1.5.1",
    "security_profile": "full"
}


@pytest.mark.django_db
def test_device_list(token_client, organizer, event, device):
    res = dict(TEST_DEV_RES)
    res["created"] = device.created.isoformat().replace('+00:00', 'Z')
    res["initialized"] = device.initialized.isoformat().replace('+00:00', 'Z')

    resp = token_client.get('/api/v1/organizers/{}/devices/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_device_detail(token_client, organizer, event, device):
    res = dict(TEST_DEV_RES)
    res["created"] = device.created.isoformat().replace('+00:00', 'Z')
    res["initialized"] = device.initialized.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/devices/{}/'.format(organizer.slug, device.device_id))
    assert resp.status_code == 200
    assert res == resp.data


TEST_DEVICE_CREATE_PAYLOAD = {
    "name": "Foobar",
    "all_events": False,
    "limit_events": ["dummy"],
}


@pytest.mark.django_db
def test_device_create(token_client, organizer, event):
    resp = token_client.post(
        '/api/v1/organizers/{}/devices/'.format(organizer.slug),
        TEST_DEVICE_CREATE_PAYLOAD,
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        d = Device.objects.get(device_id=resp.data['device_id'])
        assert list(d.limit_events.all()) == [event]
        assert d.initialization_token
        assert not d.initialized


@pytest.mark.django_db
def test_device_update(token_client, organizer, event, device):
    resp = token_client.patch(
        '/api/v1/organizers/{}/devices/{}/'.format(organizer.slug, device.device_id),
        {
            'name': 'bla',
            'hardware_brand': 'Foo'
        },
        format='json'
    )
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.hardware_brand == 'Zebra'
    assert device.name == 'bla'


@pytest.mark.django_db
def test_device_delete(token_client, organizer, event, device):
    resp = token_client.delete(
        '/api/v1/organizers/{}/devices/{}/'.format(organizer.slug, device.device_id),
    )
    assert resp.status_code == 405
    with scopes_disabled():
        assert organizer.devices.count() == 1
