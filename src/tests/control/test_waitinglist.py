#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, ItemVariation, Organizer, Quota, Team, User, Voucher,
    WaitingListEntry,
)
from pretix.control.views.dashboards import waitinglist_widgets


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,tests.testdummy'
    )
    event.settings.set('ticketoutput_testdummy__enabled', True)
    event.settings.set('waiting_list_names_asked', False)
    event.settings.set('waiting_list_names_required', False)
    event.settings.set('waiting_list_phones_asked', False)
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23, admission=True, allow_waitinglist=True)
    item2 = Item.objects.create(event=event, name="Ticket", default_price=23, admission=True)

    for i in range(5):
        WaitingListEntry.objects.create(
            event=event, item=item1, email='foo{}@bar.com'.format(i)
        )
    v = Voucher.objects.create(item=item1, event=event, block_quota=True, redeemed=1)
    WaitingListEntry.objects.create(
        event=event, item=item1, email='success@example.org', voucher=v
    )
    v = Voucher.objects.create(item=item1, event=event, block_quota=True, redeemed=0, valid_until=now() - timedelta(days=5))
    WaitingListEntry.objects.create(
        event=event, item=item2, email='expired@example.org', voucher=v
    )
    v = Voucher.objects.create(item=item1, event=event, block_quota=True, redeemed=0, valid_until=now() + timedelta(days=5))
    WaitingListEntry.objects.create(
        event=event, item=item2, email='valid@example.org', voucher=v
    )

    t = Team.objects.create(organizer=o, all_event_permissions=True)
    t.members.add(user)
    t.limit_events.add(event)

    wle = WaitingListEntry.objects.filter(item=item1).first()
    variation = ItemVariation.objects.create(item=item1)

    return {
        "event": event,
        "item1": item1,
        "wle": wle,
        "variation": variation,
    }


@pytest.mark.django_db
def test_list(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')

    response = client.get('/control/event/dummy/dummy/waitinglist/')
    assert 'success@example.org' not in response.content.decode()
    assert 'expired@example.org' not in response.content.decode()
    assert 'foo0@bar.com' in response.content.decode()
    assert 'valid@example.org' not in response.content.decode()
    assert response.context['estimate'] == 23 * 5

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=a')
    assert 'success@example.org' in response.content.decode()
    assert 'foo0@bar.com' in response.content.decode()
    assert 'expired@example.org' in response.content.decode()
    assert 'valid@example.org' in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=s')
    assert 'success@example.org' in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'expired@example.org' in response.content.decode()
    assert 'valid@example.org' in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=v')
    assert 'success@example.org' not in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'expired@example.org' not in response.content.decode()
    assert 'valid@example.org' in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=r')
    assert 'success@example.org' in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'expired@example.org' not in response.content.decode()
    assert 'valid@example.org' not in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?status=e')
    assert 'success@example.org' not in response.content.decode()
    assert 'expired@example.org' in response.content.decode()
    assert 'foo0@bar.com' not in response.content.decode()
    assert 'valid@example.org' not in response.content.decode()

    response = client.get('/control/event/dummy/dummy/waitinglist/?item=%d' % env['item1'].pk)
    assert 'item2@example.org' not in response.content.decode()
    assert 'foo0@bar.com' in response.content.decode()


@pytest.mark.django_db
def test_assign_single(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        wle = WaitingListEntry.objects.filter(voucher__isnull=True).last()

    client.post('/control/event/dummy/dummy/waitinglist/action', {
        'assign': wle.pk
    })
    wle.refresh_from_db()
    assert wle.voucher


@pytest.mark.django_db
def test_priority_single(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        wle = WaitingListEntry.objects.filter(voucher__isnull=True).last()
    assert wle.priority == 0

    client.post('/control/event/dummy/dummy/waitinglist/action', {
        'move_top': wle.pk
    })
    wle.refresh_from_db()
    assert wle.priority == 1
    client.post('/control/event/dummy/dummy/waitinglist/action', {
        'move_top': wle.pk
    })
    wle.refresh_from_db()
    assert wle.priority == 2
    client.post('/control/event/dummy/dummy/waitinglist/action', {
        'move_end': wle.pk
    })
    wle.refresh_from_db()
    assert wle.priority == -1


@pytest.mark.django_db
def test_delete_single(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        wle = WaitingListEntry.objects.first()

    client.post('/control/event/dummy/dummy/waitinglist/%s/delete' % (wle.id))
    with pytest.raises(WaitingListEntry.DoesNotExist):
        with scopes_disabled():
            WaitingListEntry.objects.get(id=wle.id)


@pytest.mark.django_db
def test_delete_bulk(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        wle = WaitingListEntry.objects.first()

    client.post('/control/event/dummy/dummy/waitinglist/action', data={
        'entry': wle.pk,
        'action': 'delete_confirm',
    })
    with pytest.raises(WaitingListEntry.DoesNotExist):
        with scopes_disabled():
            WaitingListEntry.objects.get(id=wle.id)


@pytest.mark.django_db
def test_edit_settings(client, env):
    event = env['event']
    wle = env['wle']
    client.login(email='dummy@dummy.dummy', password='dummy')

    response = client.get('/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id)
    assert ['email', 'itemvar'] == list(response.context_data['form'].fields.keys())

    event.settings.set('waiting_list_names_asked', True)
    response = client.get('/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id)
    assert 'name_parts' in list(response.context_data['form'].fields.keys())

    event.settings.set('waiting_list_names_required', True)
    response = client.get('/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id)
    assert response.context_data['form'].fields['name_parts'].required is True

    event.settings.set('waiting_list_phones_asked', True)
    response = client.get('/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id)
    assert 'phone' in list(response.context_data['form'].fields.keys())


@pytest.mark.django_db
def test_edit_itemvariation(client, env):
    item = env['item1']
    variation = env['variation']
    wle = env['wle']

    client.login(email='dummy@dummy.dummy', password='dummy')

    itemvar = f"{item.pk}-{variation.pk}"

    client.post(
        '/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id,
        data={
            "email": f"1_{wle.email}",
            "itemvar": itemvar
        }
    )

    wle.refresh_from_db()
    assert wle.variation == variation


@pytest.mark.django_db
def test_edit_validations_only_valid_item(client, env):
    item = env['item1']
    wle = env['wle']

    client.login(email='dummy@dummy.dummy', password='dummy')

    itemvar = f"{item.pk + 10000}"

    response = client.post(
        '/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id,
        data={
            "email": f"1_{wle.email}",
            "itemvar": itemvar
        }
    )
    assert response.context_data['form'].errors['itemvar'] == ["Select a valid choice."]


@pytest.mark.django_db
def test_edit_validations_only_valid_variation(client, env):
    item = env['item1']
    wle = env['wle']
    variation = env['variation']

    client.login(email='dummy@dummy.dummy', password='dummy')

    itemvar = f"{item.pk}-{variation.pk + 1}"

    response = client.post(
        '/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id,
        data={
            "email": f"1_{wle.email}",
            "itemvar": itemvar
        }
    )
    assert response.context_data['form'].errors['itemvar'] == ["Select a valid choice."]


@pytest.mark.django_db
def test_edit_validations_inactive_item(client, env):
    item = env['item1']
    wle = env['wle']
    item.active = False
    item.save()

    client.login(email='dummy@dummy.dummy', password='dummy')

    response = client.post(
        '/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id,
        data={
            "email": f"1_{wle.email}",
            "itemvar": f"{item.pk}"
        }
    )
    assert response.context_data['form'].errors['itemvar'] == ["The selected product is not active."]


@pytest.mark.django_db
def test_edit_validations_inactive_variation(client, env):
    item = env['item1']
    wle = env['wle']
    variation = env['variation']
    wle.variation = variation
    wle.save()

    variation.active = False
    variation.save()

    client.login(email='dummy@dummy.dummy', password='dummy')
    response = client.post(
        '/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id,
        data={
            "email": f"1_{wle.email}",
            "itemvar": f"{item.pk}-{variation.pk}"
        }
    )
    assert response.context_data['form'].errors['itemvar'] == ["The selected product is not active."]


@pytest.mark.django_db
def test_edit_voucher_send_out(client, env):
    event = env['event']
    item = env['item1']
    wle = env['wle']

    quota = Quota.objects.create(event=event, size=100)
    quota.items.add(item)

    client.login(email='dummy@dummy.dummy', password='dummy')

    with scopes_disabled():
        wle.send_voucher()

    response = client.post(
        '/control/event/dummy/dummy/waitinglist/%s/edit' % wle.id,
        data={
            "email": f"1_{wle.email}",
            "itemvar": item.pk
        },
        follow=True
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_dashboard(client, env):
    with scopes_disabled():
        quota = Quota.objects.create(name="Test", size=2, event=env['event'])
        quota.items.add(env['item1'])
        w = waitinglist_widgets(env['event'])

    assert '1' in w[0]['content']
    assert '5' in w[1]['content']
