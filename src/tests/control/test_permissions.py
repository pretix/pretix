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
# This file contains Apache-licensed contributions copyrighted by: Maico Timmerman, Sohalt, Tobias Kunze,
# jasonwaiting@live.hk, oocf
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import time
from datetime import timedelta

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Order, Organizer, Team, User


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    Order.objects.create(
        code='FOO', event=event,
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        total=0,
    )
    Team.objects.create(pk=1, organizer=o)
    return event, user, o


superuser_urls = [
    "global/settings/",
    "logdetail/",
    "logdetail/payment/",
    "logdetail/refund/",
    "users/select2",
    "users/",
    "users/add",
    "users/1/",
    "users/1/impersonate",
    "users/1/reset",
    "sudo/sessions/",
]

staff_urls = [
    "global/update/",
    "sudo/",
    "sudo/2/",
]

event_urls = [
    "",
    "comment/",
    "live/",
    "delete/",
    "dangerzone/",
    "cancel/",
    "settings/",
    "settings/plugins",
    "settings/payment",
    "settings/tickets",
    "settings/email",
    "settings/email/setup",
    "settings/cancel",
    "settings/invoice",
    "settings/invoice/preview",
    "settings/widget",
    "settings/tax/",
    "settings/tax/add",
    "settings/tax/1/",
    "settings/tax/1/delete",
    "items/",
    "items/add",
    "items/1/",
    "items/1/up",
    "items/1/down",
    "items/1/delete",
    "categories/",
    "categories/add",
    "categories/2/",
    "categories/2/up",
    "categories/2/down",
    "categories/2/delete",
    "discounts/",
    "discounts/add",
    "discounts/2/",
    "discounts/2/up",
    "discounts/2/down",
    "discounts/2/delete",
    "questions/",
    "questions/2/delete",
    "questions/2/",
    "questions/add",
    "vouchers/",
    "vouchers/2/delete",
    "vouchers/2/",
    "vouchers/add",
    "vouchers/bulk_add",
    "vouchers/rng",
    "subevents/",
    "subevents/select2",
    "subevents/add",
    "subevents/2/delete",
    "subevents/2/",
    "quotas/",
    "quotas/2/delete",
    "quotas/2/change",
    "quotas/2/",
    "quotas/add",
    "orders/ABC/transition",
    "orders/ABC/resend",
    "orders/ABC/invoice",
    "orders/ABC/extend",
    "orders/ABC/reactivate",
    "orders/ABC/change",
    "orders/ABC/contact",
    "orders/ABC/comment",
    "orders/ABC/locale",
    "orders/ABC/approve",
    "orders/ABC/deny",
    "orders/ABC/checkvatid",
    "orders/ABC/cancellationrequests/1/delete",
    "orders/ABC/payments/1/cancel",
    "orders/ABC/payments/1/confirm",
    "orders/ABC/refund",
    "orders/ABC/refunds/1/cancel",
    "orders/ABC/refunds/1/process",
    "orders/ABC/refunds/1/done",
    "orders/ABC/delete",
    "orders/ABC/sendmail",
    "orders/ABC/1/sendmail",
    "orders/ABC/",
    "orders/",
    "orders/import/",
    "checkins/",
    "checkinlists/",
    "checkinlists/1/",
    "checkinlists/1/change",
    "checkinlists/1/delete",
    "checkinlists/1/bulk_action",
    "waitinglist/",
    "waitinglist/auto_assign",
    "waitinglist/action",
    "invoice/1",
]

organizer_urls = [
    'organizer/abc/edit',
    'organizer/abc/',
    'organizer/abc/settings/email',
    'organizer/abc/settings/email/setup',
    'organizer/abc/teams',
    'organizer/abc/team/1/',
    'organizer/abc/team/1/edit',
    'organizer/abc/team/1/delete',
    'organizer/abc/team/add',
    'organizer/abc/devices',
    'organizer/abc/device/add',
    'organizer/abc/device/bulk_edit',
    'organizer/abc/device/1/edit',
    'organizer/abc/device/1/connect',
    'organizer/abc/device/1/revoke',
    'organizer/abc/gates',
    'organizer/abc/gate/add',
    'organizer/abc/gate/1/edit',
    'organizer/abc/gate/1/delete',
    'organizer/abc/properties',
    'organizer/abc/property/add',
    'organizer/abc/property/1/edit',
    'organizer/abc/property/1/delete',
    'organizer/abc/webhooks',
    'organizer/abc/webhook/add',
    'organizer/abc/webhook/1/edit',
    'organizer/abc/webhook/1/logs',
    'organizer/abc/ssoproviders',
    'organizer/abc/ssoprovider/add',
    'organizer/abc/ssoprovider/1/edit',
    'organizer/abc/ssoprovider/1/delete',
    'organizer/abc/customers',
    'organizer/abc/customer/add',
    'organizer/abc/customer/1/',
    'organizer/abc/reusable_media',
    'organizer/abc/reusable_media/add',
    'organizer/abc/reusable_media/1/',
    'organizer/abc/reusable_media/1/edit',
    'organizer/abc/giftcards',
    'organizer/abc/giftcard/add',
    'organizer/abc/giftcard/1/',
    'organizer/abc/giftcard/1/edit',
    'organizer/abc/giftcards/acceptance',
    'organizer/abc/giftcards/acceptance/invite',
]


@pytest.fixture
def perf_patch(monkeypatch):
    # Patch out template rendering for performance improvements
    monkeypatch.setattr("django.template.backends.django.Template.render", lambda *args, **kwargs: "mocked template")


@pytest.mark.django_db
@pytest.mark.parametrize("url", [
    "",
    "settings",
    "admin/",
    "organizers/",
    "organizers/add",
    "organizers/select2",
    "events/",
    "events/add",
] + ['event/dummy/dummy/' + u for u in event_urls] + organizer_urls)
def test_logged_out(client, env, url):
    client.logout()
    response = client.get('/control/' + url)
    assert response.status_code == 302
    assert "/control/login" in response['Location']


@pytest.mark.django_db
@pytest.mark.parametrize("url", superuser_urls)
def test_superuser_required(perf_patch, client, env, url):
    client.login(email='dummy@dummy.dummy', password='dummy')
    env[1].is_staff = True
    env[1].save()
    response = client.get('/control/' + url)
    if response.status_code == 302:
        assert '/sudo/' in response['Location']
    else:
        assert response.status_code == 403
    env[1].staffsession_set.create(date_start=now(), session_key=client.session.session_key)
    response = client.get('/control/' + url)
    assert response.status_code in (200, 302, 404)


@pytest.mark.django_db
@pytest.mark.parametrize("url", staff_urls)
def test_staff_required(perf_patch, client, env, url):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/' + url)
    assert response.status_code == 403
    env[1].is_staff = True
    env[1].save()
    response = client.get('/control/' + url)
    assert response.status_code in (200, 302, 404)


@pytest.mark.django_db
@pytest.mark.parametrize("url", event_urls)
def test_wrong_event(perf_patch, client, env, url):
    event2 = Event.objects.create(
        organizer=env[2], name='Dummy', slug='dummy2',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    t = Team.objects.create(organizer=env[2], can_change_event_settings=True)
    t.members.add(env[1])
    t.limit_events.add(event2)

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/' + url)
    # These permission violations do not yield a 403 error, but
    # a 404 error to prevent information leakage
    assert response.status_code == 404


HTTP_POST = "post"
HTTP_GET = "get"

event_permission_urls = [
    ("can_change_event_settings", "live/", 200, HTTP_GET),
    ("can_change_event_settings", "delete/", 200, HTTP_GET),
    ("can_change_event_settings", "dangerzone/", 200, HTTP_GET),
    ("can_change_event_settings", "settings/", 200, HTTP_GET),
    ("can_change_event_settings", "settings/plugins", 200, HTTP_GET),
    ("can_change_event_settings", "settings/payment", 200, HTTP_GET),
    ("can_change_event_settings", "settings/tickets", 200, HTTP_GET),
    ("can_change_event_settings", "settings/email", 200, HTTP_GET),
    ("can_change_event_settings", "settings/email/setup", 200, HTTP_GET),
    ("can_change_event_settings", "settings/cancel", 200, HTTP_GET),
    ("can_change_event_settings", "settings/invoice", 200, HTTP_GET),
    ("can_change_event_settings", "settings/widget", 200, HTTP_GET),
    ("can_change_event_settings", "settings/invoice/preview", 200, HTTP_GET),
    ("can_change_event_settings", "settings/tax/", 200, HTTP_GET),
    ("can_change_event_settings", "settings/tax/1/", 404, HTTP_GET),
    ("can_change_event_settings", "settings/tax/add", 200, HTTP_GET),
    ("can_change_event_settings", "settings/tax/1/delete", 404, HTTP_GET),
    ("can_change_event_settings", "comment/", 405, HTTP_GET),
    # Lists are currently not access-controlled
    # ("can_change_items", "items/", 200),
    ("can_change_items", "items/add", 200, HTTP_GET),
    ("can_change_items", "items/1/up", 404, HTTP_POST),
    ("can_change_items", "items/1/down", 404, HTTP_POST),
    ("can_change_items", "items/reorder", 400, HTTP_POST),
    ("can_change_items", "items/1/delete", 404, HTTP_GET),
    # ("can_change_items", "categories/", 200),
    # We don't have to create categories and similar objects
    # for testing this, it is enough to test that a 404 error
    # is returned instead of a 403 one.
    ("can_change_items", "categories/2/", 404, HTTP_GET),
    ("can_change_items", "categories/2/delete", 404, HTTP_GET),
    ("can_change_items", "categories/2/up", 404, HTTP_POST),
    ("can_change_items", "categories/2/down", 404, HTTP_POST),
    ("can_change_items", "categories/reorder", 400, HTTP_POST),
    ("can_change_items", "categories/add", 200, HTTP_GET),
    # ("can_change_items", "questions/", 200, HTTP_GET),
    ("can_change_items", "questions/2/", 404, HTTP_GET),
    ("can_change_items", "questions/2/delete", 404, HTTP_GET),
    ("can_change_items", "questions/reorder", 400, HTTP_POST),
    ("can_change_items", "questions/add", 200, HTTP_GET),
    # ("can_change_items", "quotas/", 200, HTTP_GET),
    ("can_change_items", "quotas/2/change", 404, HTTP_GET),
    ("can_change_items", "quotas/2/delete", 404, HTTP_GET),
    ("can_change_items", "quotas/add", 200, HTTP_GET),
    # ("can_change_items", "discounts/", 200),
    # We don't have to create categories and similar objects
    # for testing this, it is enough to test that a 404 error
    # is returned instead of a 403 one.
    ("can_change_items", "discounts/2/", 404, HTTP_GET),
    ("can_change_items", "discounts/2/delete", 404, HTTP_GET),
    ("can_change_items", "discounts/2/up", 404, HTTP_POST),
    ("can_change_items", "discounts/2/down", 404, HTTP_POST),
    ("can_change_items", "discounts/reorder", 400, HTTP_POST),
    ("can_change_items", "discounts/add", 200, HTTP_GET),
    ("can_change_event_settings", "subevents/", 200, HTTP_GET),
    ("can_change_event_settings", "subevents/2/", 404, HTTP_GET),
    ("can_change_event_settings", "subevents/2/delete", 404, HTTP_GET),
    ("can_change_event_settings", "subevents/add", 200, HTTP_GET),
    ("can_view_orders", "orders/overview/", 200, HTTP_GET),
    ("can_view_orders", "orders/export/", 200, HTTP_GET),
    ("can_view_orders", "orders/export/do", 302, HTTP_POST),
    ("can_view_orders", "orders/", 200, HTTP_GET),
    ("can_view_orders", "orders/FOO/", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/extend", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/reactivate", 302, HTTP_GET),
    ("can_change_orders", "orders/FOO/contact", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/transition", 405, HTTP_GET),
    ("can_change_orders", "orders/FOO/checkvatid", 405, HTTP_GET),
    ("can_change_orders", "orders/FOO/resend", 405, HTTP_GET),
    ("can_change_orders", "orders/FOO/invoice", 405, HTTP_GET),
    ("can_change_orders", "orders/FOO/change", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/approve", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/deny", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/delete", 302, HTTP_GET),
    ("can_change_orders", "orders/FOO/comment", 405, HTTP_GET),
    ("can_change_orders", "orders/FOO/locale", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/sendmail", 200, HTTP_GET),
    ("can_change_orders", "orders/FOO/1/sendmail", 404, HTTP_GET),
    ("can_change_orders", "orders/import/", 200, HTTP_GET),
    ("can_change_orders", "orders/import/0ab7b081-92d3-4480-82de-2f8b056fd32f/", 404, HTTP_GET),
    ("can_view_orders", "orders/FOO/answer/5/", 404, HTTP_GET),
    ("can_change_orders", "cancel/", 200, HTTP_GET),
    ("can_change_vouchers", "vouchers/add", 200, HTTP_GET),
    ("can_change_vouchers", "vouchers/bulk_add", 200, HTTP_GET),
    ("can_view_vouchers", "vouchers/", 200, HTTP_GET),
    ("can_view_vouchers", "vouchers/tags/", 200, HTTP_GET),
    ("can_change_vouchers", "vouchers/1234/", 404, HTTP_GET),
    ("can_change_vouchers", "vouchers/1234/delete", 404, HTTP_GET),
    ("can_view_orders", "waitinglist/", 200, HTTP_GET),
    ("can_change_orders", "waitinglist/auto_assign", 405, HTTP_GET),
    ("can_change_orders", "waitinglist/action", 405, HTTP_GET),
    ("can_view_orders", "checkins/", 200, HTTP_GET),
    ("can_view_orders", "checkinlists/", 200, HTTP_GET),
    ("can_view_orders", "checkinlists/1/", 404, HTTP_GET),
    ("can_change_orders", "checkinlists/1/bulk_action", 404, HTTP_POST),
    ("can_checkin_orders", "checkinlists/1/bulk_action", 404, HTTP_POST),
    ("can_change_event_settings", "checkinlists/add", 200, HTTP_GET),
    ("can_change_event_settings", "checkinlists/1/change", 404, HTTP_GET),
    ("can_change_event_settings", "checkinlists/1/delete", 404, HTTP_GET),

    # bank transfer
    ("can_change_orders", "banktransfer/import/", 200, HTTP_GET),
    ("can_change_orders", "banktransfer/job/1/", 404, HTTP_GET),
    ("can_change_orders", "banktransfer/action/", 200, HTTP_GET),
    ("can_change_orders", "banktransfer/refunds/", 200, HTTP_GET),
    ("can_change_orders", "banktransfer/export/1/", 404, HTTP_GET),
    ("can_change_orders", "banktransfer/sepa-export/1/", 404, HTTP_GET),
]


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code,http_method", event_permission_urls)
def test_wrong_event_permission(perf_patch, client, env, perm, url, code, http_method):
    t = Team(
        organizer=env[2], all_events=True
    )
    setattr(t, perm, False)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    if http_method and http_method == HTTP_POST:
        response = client.post('/control/event/dummy/dummy/' + url)
    else:
        response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code,http_method", event_permission_urls)
def test_limited_event_permission_for_other_event(perf_patch, client, env, perm, url, code, http_method):
    event2 = Event.objects.create(
        organizer=env[2], name='Dummy', slug='dummy2',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    t = Team.objects.create(organizer=env[2], can_change_event_settings=True)
    t.members.add(env[1])
    t.limit_events.add(event2)

    client.login(email='dummy@dummy.dummy', password='dummy')
    if http_method and http_method == HTTP_POST:
        response = client.post('/control/event/dummy/dummy/' + url)
    else:
        response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_current_permission(client, env):
    t = Team(
        organizer=env[2], all_events=True
    )
    setattr(t, 'can_change_event_settings', True)
    t.save()
    t.members.add(env[1])

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/event/dummy/dummy/settings/')
    assert response.status_code == 200
    setattr(t, 'can_change_event_settings', False)
    t.save()
    response = client.get('/control/event/dummy/dummy/settings/')
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code,http_method", event_permission_urls)
def test_correct_event_permission_all_events(perf_patch, client, env, perm, url, code, http_method):
    t = Team(organizer=env[2], all_events=True)
    setattr(t, perm, True)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    session = client.session
    session['pretix_auth_login_time'] = int(time.time())
    session.save()
    if http_method and http_method == HTTP_POST:
        response = client.post('/control/event/dummy/dummy/' + url)
    else:
        response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == code


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code,http_method", event_permission_urls)
def test_correct_event_permission_limited(perf_patch, client, env, perm, url, code, http_method):
    t = Team(organizer=env[2])
    setattr(t, perm, True)
    t.save()
    t.members.add(env[1])
    t.limit_events.add(env[0])
    client.login(email='dummy@dummy.dummy', password='dummy')
    session = client.session
    session['pretix_auth_login_time'] = int(time.time())
    session.save()
    if http_method and http_method == HTTP_POST:
        response = client.post('/control/event/dummy/dummy/' + url)
    else:
        response = client.get('/control/event/dummy/dummy/' + url)
    assert response.status_code == code


@pytest.mark.django_db
@pytest.mark.parametrize("url", organizer_urls)
def test_wrong_organizer(perf_patch, client, env, url):
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/' + url)
    # These permission violations do not yield a 403 error, but
    # a 404 error to prevent information leakage
    assert response.status_code == 404


organizer_permission_urls = [
    ("can_change_teams", "organizer/dummy/teams", 200),
    ("can_change_teams", "organizer/dummy/team/add", 200),
    ("can_change_teams", "organizer/dummy/team/1/", 200),
    ("can_change_teams", "organizer/dummy/team/1/edit", 200),
    ("can_change_teams", "organizer/dummy/team/1/delete", 200),
    ("can_change_organizer_settings", "organizer/dummy/edit", 200),
    ("can_change_organizer_settings", "organizer/dummy/settings/email", 200),
    ("can_change_organizer_settings", "organizer/dummy/settings/email/setup", 200),
    ("can_change_organizer_settings", "organizer/dummy/devices", 200),
    ("can_change_organizer_settings", "organizer/dummy/devices/select2", 200),
    ("can_change_organizer_settings", "organizer/dummy/device/add", 200),
    ("can_change_organizer_settings", "organizer/dummy/device/1/edit", 404),
    ("can_change_organizer_settings", "organizer/dummy/device/1/connect", 404),
    ("can_change_organizer_settings", "organizer/dummy/device/1/revoke", 404),
    ("can_change_organizer_settings", "organizer/dummy/gates", 200),
    ("can_change_organizer_settings", "organizer/dummy/gates/select2", 200),
    ("can_change_organizer_settings", "organizer/dummy/gate/add", 200),
    ("can_change_organizer_settings", "organizer/dummy/gate/1/edit", 404),
    ("can_change_organizer_settings", "organizer/dummy/gate/1/delete", 404),
    ("can_change_organizer_settings", "organizer/dummy/properties", 200),
    ("can_change_organizer_settings", "organizer/dummy/property/add", 200),
    ("can_change_organizer_settings", "organizer/dummy/property/1/edit", 404),
    ("can_change_organizer_settings", "organizer/dummy/property/1/delete", 404),
    ("can_change_organizer_settings", "organizer/dummy/membershiptypes", 200),
    ("can_change_organizer_settings", "organizer/dummy/membershiptype/add", 200),
    ("can_change_organizer_settings", "organizer/dummy/membershiptype/1/edit", 404),
    ("can_change_organizer_settings", "organizer/dummy/membershiptype/1/delete", 404),
    ("can_change_organizer_settings", "organizer/dummy/ssoproviders", 200),
    ("can_change_organizer_settings", "organizer/dummy/ssoprovider/add", 200),
    ("can_change_organizer_settings", "organizer/dummy/ssoprovider/1/edit", 404),
    ("can_change_organizer_settings", "organizer/dummy/ssoprovider/1/delete", 404),
    ("can_manage_customers", "organizer/dummy/customers", 200),
    ("can_manage_customers", "organizer/dummy/customer/ABC/edit", 404),
    ("can_manage_customers", "organizer/dummy/customer/ABC/anonymize", 404),
    ("can_manage_customers", "organizer/dummy/customer/ABC/membership/add", 404),
    ("can_manage_customers", "organizer/dummy/customer/ABC/membership/1/edit", 404),
    ("can_manage_customers", "organizer/dummy/customer/ABC/", 404),
    ("can_manage_reusable_media", "organizer/dummy/reusable_media", 200),
    ("can_manage_reusable_media", "organizer/dummy/reusable_media/1/edit", 404),
    ("can_manage_reusable_media", "organizer/dummy/reusable_media/1/", 404),
    ("can_manage_gift_cards", "organizer/dummy/giftcards", 200),
    ("can_manage_gift_cards", "organizer/dummy/giftcard/add", 200),
    ("can_manage_gift_cards", "organizer/dummy/giftcard/1/", 404),
    ("can_manage_gift_cards", "organizer/dummy/giftcard/1/edit", 404),
    ("can_change_organizer_settings", "organizer/dummy/giftcards/acceptance", 200),
    ("can_change_organizer_settings", "organizer/dummy/giftcards/acceptance/invite", 200),

    # bank transfer
    ("can_change_orders", "organizer/dummy/banktransfer/import/", 200),
    ("can_change_orders", "organizer/dummy/banktransfer/job/1/", 404),
    ("can_change_orders", "organizer/dummy/banktransfer/action/", 200),
    ("can_change_orders", "organizer/dummy/banktransfer/refunds/", 200),
    ("can_change_orders", "organizer/dummy/banktransfer/export/1/", 404),
    ("can_change_orders", "organizer/dummy/banktransfer/sepa-export/1/", 404),
]


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", organizer_permission_urls)
def test_wrong_organizer_permission(perf_patch, client, env, perm, url, code):
    t = Team(organizer=env[2])
    setattr(t, perm, False)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.get('/control/' + url)
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("perm,url,code", organizer_permission_urls)
def test_correct_organizer_permission(perf_patch, client, env, perm, url, code):
    t = Team(organizer=env[2])
    setattr(t, perm, True)
    t.save()
    t.members.add(env[1])
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.session['pretix_auth_login_time'] = int(time.time())
    client.session.save()
    response = client.get('/control/' + url)
    assert response.status_code == code
