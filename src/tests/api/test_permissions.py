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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Ture Gjørup
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import time

import pytest
from django.test import override_settings
from django.utils.timezone import now

from pretix.base.models import Organizer

event_urls = [
    (None, ''),
    (None, 'categories/'),
    ('can_view_orders', 'invoices/'),
    (None, 'items/'),
    ('can_view_orders', 'orders/'),
    ('can_view_orders', 'orderpositions/'),
    (None, 'questions/'),
    (None, 'quotas/'),
    ('can_view_vouchers', 'vouchers/'),
    (None, 'subevents/'),
    (None, 'taxrules/'),
    ('can_view_orders', 'waitinglistentries/'),
    ('can_view_orders', 'checkinlists/'),
]

event_permission_sub_urls = [
    ('get', 'can_change_event_settings', 'settings/', 200),
    ('patch', 'can_change_event_settings', 'settings/', 200),
    ('get', 'can_view_orders', 'revokedsecrets/', 200),
    ('get', 'can_view_orders', 'revokedsecrets/1/', 404),
    ('get', 'can_view_orders', 'blockedsecrets/', 200),
    ('get', 'can_view_orders', 'blockedsecrets/1/', 404),
    ('get', 'can_view_orders', 'orders/', 200),
    ('get', 'can_view_orders', 'orderpositions/', 200),
    ('delete', 'can_change_orders', 'orderpositions/1/', 404),
    ('post', 'can_change_orders', 'orderpositions/1/price_calc/', 404),
    ('get', 'can_view_vouchers', 'vouchers/', 200),
    ('get', 'can_view_orders', 'invoices/', 200),
    ('get', 'can_view_orders', 'invoices/1/', 404),
    ('post', 'can_change_orders', 'invoices/1/regenerate/', 404),
    ('post', 'can_change_orders', 'invoices/1/reissue/', 404),
    ('get', 'can_view_orders', 'waitinglistentries/', 200),
    ('get', 'can_view_orders', 'waitinglistentries/1/', 404),
    ('post', 'can_change_orders', 'waitinglistentries/', 400),
    ('delete', 'can_change_orders', 'waitinglistentries/1/', 404),
    ('patch', 'can_change_orders', 'waitinglistentries/1/', 404),
    ('put', 'can_change_orders', 'waitinglistentries/1/', 404),
    ('post', 'can_change_orders', 'waitinglistentries/1/send_voucher/', 404),
    ('get', None, 'categories/', 200),
    ('get', None, 'items/', 200),
    ('get', None, 'questions/', 200),
    ('get', None, 'quotas/', 200),
    ('get', None, 'discounts/', 200),
    ('post', 'can_change_items', 'items/', 400),
    ('get', None, 'items/1/', 404),
    ('put', 'can_change_items', 'items/1/', 404),
    ('patch', 'can_change_items', 'items/1/', 404),
    ('delete', 'can_change_items', 'items/1/', 404),
    ('post', 'can_change_items', 'categories/', 400),
    ('get', None, 'categories/1/', 404),
    ('put', 'can_change_items', 'categories/1/', 404),
    ('patch', 'can_change_items', 'categories/1/', 404),
    ('delete', 'can_change_items', 'categories/1/', 404),
    ('post', 'can_change_items', 'discounts/', 400),
    ('get', None, 'discounts/1/', 404),
    ('put', 'can_change_items', 'discounts/1/', 404),
    ('patch', 'can_change_items', 'discounts/1/', 404),
    ('delete', 'can_change_items', 'discounts/1/', 404),
    ('post', 'can_change_items', 'items/1/variations/', 404),
    ('get', None, 'items/1/variations/', 404),
    ('get', None, 'items/1/variations/1/', 404),
    ('put', 'can_change_items', 'items/1/variations/1/', 404),
    ('patch', 'can_change_items', 'items/1/variations/1/', 404),
    ('delete', 'can_change_items', 'items/1/variations/1/', 404),
    ('get', None, 'items/1/addons/', 404),
    ('get', None, 'items/1/addons/1/', 404),
    ('post', 'can_change_items', 'items/1/addons/', 404),
    ('put', 'can_change_items', 'items/1/addons/1/', 404),
    ('patch', 'can_change_items', 'items/1/addons/1/', 404),
    ('delete', 'can_change_items', 'items/1/addons/1/', 404),
    ('get', None, 'subevents/', 200),
    ('get', None, 'subevents/1/', 404),
    ('get', None, 'taxrules/', 200),
    ('get', None, 'taxrules/1/', 404),
    ('post', 'can_change_event_settings', 'taxrules/', 400),
    ('put', 'can_change_event_settings', 'taxrules/1/', 404),
    ('patch', 'can_change_event_settings', 'taxrules/1/', 404),
    ('delete', 'can_change_event_settings', 'taxrules/1/', 404),
    ('get', 'can_change_event_settings', 'sendmail_rules/', 200),
    ('get', 'can_change_event_settings', 'sendmail_rules/1/', 404),
    ('post', 'can_change_event_settings', 'sendmail_rules/', 400),
    ('put', 'can_change_event_settings', 'sendmail_rules/1/', 404),
    ('patch', 'can_change_event_settings', 'sendmail_rules/1/', 404),
    ('delete', 'can_change_event_settings', 'sendmail_rules/1/', 404),
    ('get', 'can_view_vouchers', 'vouchers/', 200),
    ('get', 'can_view_vouchers', 'vouchers/1/', 404),
    ('post', 'can_change_vouchers', 'vouchers/', 201),
    ('put', 'can_change_vouchers', 'vouchers/1/', 404),
    ('patch', 'can_change_vouchers', 'vouchers/1/', 404),
    ('delete', 'can_change_vouchers', 'vouchers/1/', 404),
    ('get', None, 'quotas/', 200),
    ('get', None, 'quotas/1/', 404),
    ('post', 'can_change_items', 'quotas/', 400),
    ('put', 'can_change_items', 'quotas/1/', 404),
    ('patch', 'can_change_items', 'quotas/1/', 404),
    ('delete', 'can_change_items', 'quotas/1/', 404),
    ('get', None, 'questions/', 200),
    ('get', None, 'questions/1/', 404),
    ('post', 'can_change_items', 'questions/', 400),
    ('put', 'can_change_items', 'questions/1/', 404),
    ('patch', 'can_change_items', 'questions/1/', 404),
    ('delete', 'can_change_items', 'questions/1/', 404),
    ('get', None, 'questions/1/options/', 404),
    ('get', None, 'questions/1/options/1/', 404),
    ('put', 'can_change_items', 'questions/1/options/1/', 404),
    ('patch', 'can_change_items', 'questions/1/options/1/', 404),
    ('delete', 'can_change_items', 'questions/1/options/1/', 404),
    ('post', 'can_change_orders', 'orders/', 400),
    ('patch', 'can_change_orders', 'orders/ABC12/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_paid/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_pending/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_expired/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/mark_canceled/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/approve/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/deny/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/extend/', 400),
    ('post', 'can_change_orders', 'orders/ABC12/create_invoice/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/resend_link/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/regenerate_secrets/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/payments/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/payments/1/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/refunds/', 404),
    ('get', 'can_view_orders', 'orders/ABC12/refunds/1/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/payments/1/confirm/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/payments/1/refund/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/payments/1/cancel/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/refunds/1/cancel/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/refunds/1/process/', 404),
    ('post', 'can_change_orders', 'orders/ABC12/refunds/1/done/', 404),
    ('get', 'can_view_orders', 'checkinlists/', 200),
    ('post', 'can_change_orders', 'checkinlists/1/failed_checkins/', 400),
    ('post', 'can_change_event_settings', 'checkinlists/', 400),
    ('put', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('patch', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('delete', 'can_change_event_settings', 'checkinlists/1/', 404),
    ('get', 'can_view_orders', 'checkinlists/1/positions/', 404),
    ('post', 'can_change_orders', 'checkinlists/1/positions/3/redeem/', 404),
    ('post', 'can_create_events', 'clone/', 400),
    ('get', 'can_view_orders', 'cartpositions/', 200),
    ('get', 'can_view_orders', 'cartpositions/1/', 404),
    ('post', 'can_change_orders', 'cartpositions/', 400),
    ('delete', 'can_change_orders', 'cartpositions/1/', 404),
    ('post', 'can_view_orders', 'exporters/invoicedata/run/', 400),
    ('get', 'can_view_orders', 'exporters/invoicedata/download/bc3f9884-26ee-425b-8636-80613f84b6fa/3cb49ae6-eda3'
                               '-4605-814e-099e23777b36/', 404),
    ('get', None, 'item_meta_properties/', 200),
    ('get', None, 'item_meta_properties/0/', 404),
    ('post', 'can_change_event_settings', 'item_meta_properties/', 400),
    ('patch', 'can_change_event_settings', 'item_meta_properties/0/', 404),
    ('delete', 'can_change_event_settings', 'item_meta_properties/0/', 404),
]

org_permission_sub_urls = [
    ('get', 'can_change_organizer_settings', 'settings/', 200),
    ('patch', 'can_change_organizer_settings', 'settings/', 200),
    ('get', 'can_change_organizer_settings', 'webhooks/', 200),
    ('post', 'can_change_organizer_settings', 'webhooks/', 400),
    ('get', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('put', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('patch', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('delete', 'can_change_organizer_settings', 'webhooks/1/', 404),
    ('get', 'can_manage_customers', 'customers/', 200),
    ('post', 'can_manage_customers', 'customers/', 201),
    ('get', 'can_manage_customers', 'customers/1/', 404),
    ('patch', 'can_manage_customers', 'customers/1/', 404),
    ('post', 'can_manage_customers', 'customers/1/anonymize/', 404),
    ('put', 'can_manage_customers', 'customers/1/', 404),
    ('delete', 'can_manage_customers', 'customers/1/', 404),
    ('get', 'can_manage_customers', 'memberships/', 200),
    ('post', 'can_manage_customers', 'memberships/', 400),
    ('get', 'can_manage_customers', 'memberships/1/', 404),
    ('patch', 'can_manage_customers', 'memberships/1/', 404),
    ('put', 'can_manage_customers', 'memberships/1/', 404),
    ('delete', 'can_manage_customers', 'memberships/1/', 404),
    ('get', 'can_change_organizer_settings', 'membershiptypes/', 200),
    ('post', 'can_change_organizer_settings', 'membershiptypes/', 400),
    ('get', 'can_change_organizer_settings', 'membershiptypes/1/', 404),
    ('patch', 'can_change_organizer_settings', 'membershiptypes/1/', 404),
    ('put', 'can_change_organizer_settings', 'membershiptypes/1/', 404),
    ('delete', 'can_change_organizer_settings', 'membershiptypes/1/', 404),
    ('get', 'can_manage_gift_cards', 'giftcards/', 200),
    ('post', 'can_manage_gift_cards', 'giftcards/', 400),
    ('get', 'can_manage_gift_cards', 'giftcards/1/', 404),
    ('put', 'can_manage_gift_cards', 'giftcards/1/', 404),
    ('patch', 'can_manage_gift_cards', 'giftcards/1/', 404),
    ('get', 'can_manage_gift_cards', 'giftcards/1/transactions/', 404),
    ('get', 'can_manage_gift_cards', 'giftcards/1/transactions/1/', 404),
    ('get', 'can_change_organizer_settings', 'devices/', 200),
    ('post', 'can_change_organizer_settings', 'devices/', 400),
    ('get', 'can_change_organizer_settings', 'devices/1/', 404),
    ('put', 'can_change_organizer_settings', 'devices/1/', 404),
    ('patch', 'can_change_organizer_settings', 'devices/1/', 404),
    ('get', 'can_change_teams', 'teams/', 200),
    ('post', 'can_change_teams', 'teams/', 400),
    ('get', 'can_change_teams', 'teams/{team_id}/', 200),
    ('put', 'can_change_teams', 'teams/{team_id}/', 400),
    ('patch', 'can_change_teams', 'teams/{team_id}/', 200),
    ('get', 'can_change_teams', 'teams/{team_id}/members/', 200),
    ('delete', 'can_change_teams', 'teams/{team_id}/members/2/', 404),
    ('get', 'can_change_teams', 'teams/{team_id}/invites/', 200),
    ('get', 'can_change_teams', 'teams/{team_id}/invites/2/', 404),
    ('delete', 'can_change_teams', 'teams/{team_id}/invites/2/', 404),
    ('post', 'can_change_teams', 'teams/{team_id}/invites/', 400),
    ('get', 'can_change_teams', 'teams/{team_id}/tokens/', 200),
    ('get', 'can_change_teams', 'teams/{team_id}/tokens/0/', 404),
    ('delete', 'can_change_teams', 'teams/{team_id}/tokens/0/', 404),
    ('post', 'can_change_teams', 'teams/{team_id}/tokens/', 400),
]


event_permission_root_urls = [
    ('post', 'can_create_events', 400),
    ('put', 'can_change_event_settings', 400),
    ('patch', 'can_change_event_settings', 200),
    ('delete', 'can_change_event_settings', 204),
]


@pytest.fixture
def token_client(client, team):
    team.can_view_orders = True
    team.can_view_vouchers = True
    team.can_change_items = True
    team.save()
    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)
    return client


@pytest.mark.django_db
def test_organizer_allowed(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_organizer_not_allowed(token_client, organizer):
    o2 = Organizer.objects.create(slug='o2', name='Organizer 2')
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(o2.slug))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_organizer_not_allowed_device(device_client, organizer):
    o2 = Organizer.objects.create(slug='o2', name='Organizer 2')
    resp = device_client.get('/api/v1/organizers/{}/events/'.format(o2.slug))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_organizer_not_existing(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format('o2'))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_all_events(token_client, team, organizer, event, url):
    team.all_events = True
    team.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_all_events_device(device_client, device, organizer, event, url):
    resp = device_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    if url[0] is None or url[0] in device.permission_set():
        assert resp.status_code == 200
    else:
        assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_limit_events(token_client, organizer, team, event, url):
    team.all_events = False
    team.save()
    team.limit_events.add(event)
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_allowed_limit_events_device(device_client, organizer, device, event, url):
    device.all_events = False
    device.save()
    device.limit_events.add(event)
    resp = device_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    if url[0] is None or url[0] in device.permission_set():
        assert resp.status_code == 200
    else:
        assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_allowed(token_client, organizer, team, event, url):
    team.all_events = False
    team.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_allowed_device(device_client, organizer, device, event, url):
    device.all_events = False
    device.save()
    resp = device_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_not_existing(token_client, organizer, url, event):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_sub_urls)
def test_token_event_subresources_permission_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    if urlset[1]:
        setattr(team, urlset[1], True)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/{}'.format(
        organizer.slug, event.slug, urlset[2]))
    assert resp.status_code == urlset[3]


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_sub_urls)
def test_token_event_subresources_permission_not_allowed(token_client, team, organizer, event, urlset):
    if urlset[1] is None:
        team.all_events = False
    else:
        team.all_events = True
        setattr(team, urlset[1], False)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/{}'.format(
        organizer.slug, event.slug, urlset[2]))
    if urlset[3] == 404:
        assert resp.status_code == 403
    else:
        assert resp.status_code in (404, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_root_urls)
def test_token_event_permission_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    setattr(team, urlset[1], True)
    team.save()
    if urlset[0] == 'post':
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/'.format(organizer.slug))
    else:
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == urlset[2]


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_root_urls)
def test_token_event_permission_not_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    setattr(team, urlset[1], False)
    team.save()
    if urlset[0] == 'post':
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/'.format(organizer.slug))
    else:
        resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_log_out_after_absolute_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 403


@pytest.mark.django_db
def test_dont_logout_before_absolute_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 + 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(PRETIX_LONG_SESSIONS=False)
def test_ignore_long_session_if_disabled_in_config(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 403


@pytest.mark.django_db
def test_dont_logout_in_long_session(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
def test_log_out_after_relative_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
    session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 403


@pytest.mark.django_db
def test_dont_logout_before_relative_timeout(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
    session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 + 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
def test_dont_logout_by_relative_in_long_session(user_client, team, organizer, event):
    session = user_client.session
    session['pretix_auth_long_session'] = True
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 5
    session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200


@pytest.mark.django_db
def test_update_session_activity(user_client, team, organizer, event):
    t1 = int(time.time()) - 5
    session = user_client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = int(time.time()) - 3600 * 5
    session['pretix_auth_last_used'] = t1
    session.save()

    response = user_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert response.status_code == 200

    assert user_client.session['pretix_auth_last_used'] > t1


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", event_permission_sub_urls)
def test_device_subresource_permission_check(device_client, device, organizer, event, urlset):
    if urlset == ('get', 'can_change_event_settings', 'settings/', 200):
        return
    resp = getattr(device_client, urlset[0])('/api/v1/organizers/{}/events/{}/{}'.format(
        organizer.slug, event.slug, urlset[2]))
    if urlset[1] is None or urlset[1] in device.permission_set():
        assert resp.status_code == urlset[3]
    else:
        if urlset[3] == 404:
            assert resp.status_code == 403
        else:
            assert resp.status_code in (404, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", org_permission_sub_urls)
def test_token_org_subresources_permission_allowed(token_client, team, organizer, event, urlset):
    team.all_events = True
    if urlset[1]:
        setattr(team, urlset[1], True)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/{}'.format(
        organizer.slug, urlset[2].format(team_id=team.pk)))
    assert resp.status_code == urlset[3]


@pytest.mark.django_db
@pytest.mark.parametrize("urlset", org_permission_sub_urls)
def test_token_org_subresources_permission_not_allowed(token_client, team, organizer, event, urlset):
    if urlset[1] is None:
        team.all_events = False
    else:
        team.all_events = True
        setattr(team, urlset[1], False)
    team.save()
    resp = getattr(token_client, urlset[0])('/api/v1/organizers/{}/{}'.format(
        organizer.slug, urlset[2].format(team_id=team.pk)))
    if urlset[3] == 404:
        assert resp.status_code == 403
    else:
        assert resp.status_code in (404, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_event_staff_requires_staff_session(user_client, organizer, team, event, url, user):
    team.delete()
    user.is_staff = True
    user.save()

    resp = user_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 403
    user.staffsession_set.create(date_start=now(), session_key=user_client.session.session_key)
    resp = user_client.get('/api/v1/organizers/{}/events/{}/{}'.format(organizer.slug, event.slug, url[1]))
    assert resp.status_code == 200
