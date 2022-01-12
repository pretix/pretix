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
import json

import pytest
import responses

from pretix.base.models import User
from pretix.base.settings import GlobalSettingsObject


@pytest.fixture
def user():
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    return user


def request_callback_updatable(request):
    json_data = json.loads(request.body.decode())
    resp_body = {
        'status': 'ok',
        'version': {
            'latest': '1000.0.0',
            'yours': json_data.get('version'),
            'updatable': True
        },
        'plugins': {}
    }
    return 200, {'Content-Type': 'text/json'}, json.dumps(resp_body)


@pytest.mark.django_db
def test_update_notice_displayed(client, user):
    client.login(email='dummy@dummy.dummy', password='dummy')

    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' not in r.content.decode()

    user.is_staff = True
    user.save()
    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' in r.content.decode()

    client.get('/control/global/update/')  # Click it
    r = client.get('/control/')
    assert 'pretix automatically checks for updates in the background' not in r.content.decode()


@pytest.mark.django_db
def test_settings(client, user):
    user.is_staff = True
    user.save()
    client.login(email='dummy@dummy.dummy', password='dummy')

    client.post('/control/global/update/', {'update_check_email': 'test@example.org', 'update_check_perform': 'on'})
    gs = GlobalSettingsObject()
    gs.settings.flush()
    assert gs.settings.update_check_perform
    assert gs.settings.update_check_email

    client.post('/control/global/update/', {'update_check_email': '', 'update_check_perform': ''})
    gs.settings.flush()
    assert not gs.settings.update_check_perform
    assert not gs.settings.update_check_email


@pytest.mark.django_db
@responses.activate
def test_trigger(client, user):
    responses.add_callback(
        responses.POST, 'https://pretix.eu/.update_check/',
        callback=request_callback_updatable,
        content_type='application/json',
        match_querystring=None,  # https://github.com/getsentry/responses/issues/464
    )

    user.is_staff = True
    user.save()
    client.login(email='dummy@dummy.dummy', password='dummy')

    gs = GlobalSettingsObject()
    assert not gs.settings.update_check_last
    client.post('/control/global/update/', {'trigger': 'on'})
    gs.settings.flush()
    assert gs.settings.update_check_last
