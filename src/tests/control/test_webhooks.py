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

from pretix.api.models import WebHook
from pretix.base.models import Event, Organizer, Team, User


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def event(organizer):
    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def webhook(organizer, event):
    wh = organizer.webhooks.create(
        enabled=True,
        target_url='https://google.com',
        all_events=False
    )
    wh.limit_events.add(event)
    wh.listeners.create(action_type='pretix.event.order.placed')
    wh.listeners.create(action_type='pretix.event.order.paid')
    return wh


@pytest.fixture
def admin_user(admin_team):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team.members.add(u)
    return u


@pytest.fixture
def admin_team(organizer):
    return Team.objects.create(organizer=organizer, can_change_organizer_settings=True, name='Admin team')


@pytest.mark.django_db
def test_list_of_webhooks(event, admin_user, client, webhook):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/webhooks')
    assert 'https://google.com' in resp.content.decode()


@pytest.mark.django_db
def test_create_webhook(event, admin_user, admin_team, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/webhook/add', {
        'target_url': 'https://google.com',
        'enabled': 'on',
        'events': 'pretix.event.order.paid',
        'limit_events': str(event.pk),
    }, follow=True)
    with scopes_disabled():
        w = WebHook.objects.last()
        assert w.target_url == "https://google.com"
        assert w.limit_events.count() == 1
        assert list(w.listeners.values_list('action_type', flat=True)) == ['pretix.event.order.paid']
        assert not w.all_events


@pytest.mark.django_db
def test_update_webhook(event, admin_user, admin_team, webhook, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/webhook/{}/edit'.format(webhook.pk), {
        'target_url': 'https://google.com',
        'enabled': 'on',
        'events': ['pretix.event.order.paid', 'pretix.event.order.canceled'],
        'limit_events': str(event.pk),
    }, follow=True)
    webhook.refresh_from_db()
    assert webhook.target_url == "https://google.com"
    with scopes_disabled():
        assert webhook.limit_events.count() == 1
        assert list(webhook.listeners.values_list('action_type', flat=True)) == ['pretix.event.order.canceled',
                                                                                 'pretix.event.order.paid']
        assert not webhook.all_events


@pytest.mark.django_db
def test_webhook_logs(event, admin_user, admin_team, webhook, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    webhook.calls.create(
        webhook=webhook,
        action_type='pretix.event.order.paid',
        target_url=webhook.target_url,
        is_retry=False,
        execution_time=2,
        return_code=0,
        payload='foo',
        response_body='bar'
    )
    resp = client.get('/control/organizer/dummy/webhook/{}/logs'.format(webhook.pk))
    assert 'pretix.event.order.paid' in resp.content.decode()
