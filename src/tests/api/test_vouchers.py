import copy
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pytz import UTC

from pretix.base.models import Event, SeatingPlan, Voucher


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def voucher(event, item):
    return event.vouchers.create(item=item, price_mode='set', value=12, tag='Foo')


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(item)
    return q


TEST_VOUCHER_RES = {
    'id': 1,
    'code': '43K6LKM37FBVR2YG',
    'max_usages': 1,
    'redeemed': 0,
    'valid_until': None,
    'block_quota': False,
    'allow_ignore_quota': False,
    'price_mode': 'set',
    'value': '12.00',
    'item': 1,
    'variation': None,
    'quota': None,
    'tag': 'Foo',
    'comment': '',
    'show_hidden_items': True,
    'subevent': None,
    'seat': None,
}


@pytest.mark.django_db
def test_voucher_list(token_client, organizer, event, voucher, item, quota, subevent):
    res = dict(TEST_VOUCHER_RES)
    res['item'] = item.pk
    res['id'] = voucher.pk
    res['code'] = voucher.code
    q2 = copy.copy(quota)
    q2.pk = None
    q2.save()
    i2 = copy.copy(item)
    i2.pk = None
    i2.save()
    with scopes_disabled():
        var2 = i2.variations.create(value="foo")

    resp = token_client.get('/api/v1/organizers/{}/events/{}/vouchers/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?code={}'.format(organizer.slug, event.slug, voucher.code)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?code=ABC'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?max_usages=1'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?max_usages=2'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?redeemed=0'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?redeemed=1'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?block_quota=false'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?block_quota=true'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?allow_ignore_quota=false'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?allow_ignore_quota=true'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?price_mode=set'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?price_mode=percent'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?value=12.00'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?value=10.00'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?item={}'.format(organizer.slug, event.slug, item.pk)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?item={}'.format(organizer.slug, event.slug, i2.pk)
    )
    assert [] == resp.data['results']

    with scopes_disabled():
        var = item.variations.create(value='VIP')
        voucher.variation = var
        voucher.save()
    res['variation'] = var.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?variation={}'.format(organizer.slug, event.slug, var.pk)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?variation={}'.format(organizer.slug, event.slug, var2.pk)
    )
    assert [] == resp.data['results']

    voucher.variation = None
    voucher.item = None
    voucher.quota = quota
    voucher.save()
    res['variation'] = None
    res['item'] = None
    res['quota'] = quota.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?quota={}'.format(organizer.slug, event.slug, quota.pk)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?quota={}'.format(organizer.slug, event.slug, q2.pk)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?tag=Foo'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?tag=bar'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?active=true'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?active=false'.format(organizer.slug, event.slug)
    )
    assert [] == resp.data['results']

    voucher.redeemed = 1
    voucher.save()
    res['redeemed'] = 1
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?active=false'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']

    voucher.redeemed = 0
    voucher.valid_until = (timezone.now() - datetime.timedelta(days=1)).replace(microsecond=0)
    voucher.save()
    res['valid_until'] = voucher.valid_until.isoformat().replace('+00:00', 'Z')
    res['redeemed'] = 0
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?active=false'.format(organizer.slug, event.slug)
    )
    assert [res] == resp.data['results']

    voucher.subevent = subevent
    voucher.save()
    res['subevent'] = subevent.pk

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert [res] == resp.data['results']
    with scopes_disabled():
        se2 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?subevent={}'.format(organizer.slug, event.slug,
                                                                       se2.pk))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_voucher_detail(token_client, organizer, event, voucher, item):
    res = dict(TEST_VOUCHER_RES)
    res['item'] = item.pk
    res['id'] = voucher.pk
    res['code'] = voucher.code

    resp = token_client.get('/api/v1/organizers/{}/events/{}/vouchers/{}/'.format(organizer.slug, event.slug,
                                                                                  voucher.pk))
    assert resp.status_code == 200
    assert res == resp.data


def create_voucher(token_client, organizer, event, data, expected_failure=False):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/vouchers/'.format(organizer.slug, event.slug),
        data=data, format='json'
    )
    if expected_failure:
        assert resp.status_code == 400
    else:
        assert resp.status_code == 201
        with scopes_disabled():
            return Voucher.objects.get(pk=resp.data['id'])


@pytest.mark.django_db
def test_voucher_require_item(token_client, organizer, event, item):
    create_voucher(
        token_client, organizer, event,
        data={},
        expected_failure=True
    )


@pytest.mark.django_db
def test_voucher_create_minimal(token_client, organizer, event, item):
    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
        },
    )
    assert v.item == item


@pytest.mark.django_db
def test_voucher_create_full(token_client, organizer, event, item):
    v = create_voucher(
        token_client, organizer, event,
        data={
            'code': 'ABCDEFGHI',
            'max_usages': 1,
            'valid_until': None,
            'block_quota': False,
            'allow_ignore_quota': False,
            'price_mode': 'set',
            'value': '12.00',
            'item': item.pk,
            'variation': None,
            'quota': None,
            'tag': 'Foo',
            'comment': '',
            'subevent': None
        },
    )

    assert v.code == 'ABCDEFGHI'
    assert v.max_usages == 1
    assert v.redeemed == 0
    assert v.valid_until is None
    assert v.max_usages == 1
    assert v.block_quota is False
    assert v.price_mode == 'set'
    assert v.value == Decimal('12.00')
    assert v.item == item
    assert v.variation is None
    assert v.quota is None
    assert v.tag == 'Foo'
    assert v.subevent is None


@pytest.mark.django_db
def test_voucher_create_for_addon_item(token_client, organizer, event, item):
    c = event.categories.create(name="Foo", is_addon=True)
    item.category = c
    item.save()
    create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
        }, expected_failure=True
    )


@pytest.mark.django_db
def test_create_non_blocking_item_voucher(token_client, organizer, event, item):
    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
        }
    )
    assert v.item == item
    assert v.variation is None
    assert v.quota is None


@pytest.mark.django_db
def test_create_non_blocking_variation_voucher(token_client, organizer, event, item):
    with scopes_disabled():
        variation = item.variations.create(value="XL")
    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'variation': variation.pk
        }
    )
    assert v.item == variation.item
    assert v.variation == variation
    assert v.quota is None


@pytest.mark.django_db
def test_create_non_blocking_quota_voucher(token_client, organizer, event, quota):
    v = create_voucher(
        token_client, organizer, event,
        data={
            'quota': quota.pk
        }
    )
    assert not v.block_quota
    assert v.quota == quota
    assert v.item is None


@pytest.mark.django_db
def test_create_blocking_item_voucher_quota_free(token_client, organizer, event, item, quota):
    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'block_quota': True
        }
    )
    assert v.block_quota


@pytest.mark.django_db
def test_create_blocking_item_voucher_quota_full(token_client, organizer, event, item, quota):
    quota.size = 0
    quota.save()
    create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'block_quota': True
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_create_blocking_item_voucher_quota_full_invalid(token_client, organizer, event, item, quota):
    quota.size = 0
    quota.save()
    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'block_quota': True,
            'valid_until': (now() - datetime.timedelta(days=3)).isoformat()
        }
    )
    assert v.block_quota
    assert not v.is_active()


@pytest.mark.django_db
def test_create_blocking_variation_voucher_quota_free(token_client, organizer, event, item, quota):
    with scopes_disabled():
        variation = item.variations.create(value="XL")
    quota.variations.add(variation)
    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'variation': variation.pk,
            'block_quota': True
        }
    )
    assert v.block_quota


@pytest.mark.django_db
def test_create_short_code(token_client, organizer, event, item):
    create_voucher(
        token_client, organizer, event,
        data={
            'code': 'ABC',
            'item': item.pk
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_create_blocking_variation_voucher_quota_full(token_client, organizer, event, item, quota):
    with scopes_disabled():
        variation = item.variations.create(value="XL")
    quota.variations.add(variation)
    quota.size = 0
    quota.save()
    create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'variation': variation.pk,
            'block_quota': True
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_create_blocking_quota_voucher_quota_free(token_client, organizer, event, quota):
    create_voucher(
        token_client, organizer, event,
        data={
            'quota': quota.pk,
            'block_quota': True
        },
    )


@pytest.mark.django_db
def test_create_blocking_quota_voucher_quota_full(token_client, organizer, event, quota):
    quota.size = 0
    quota.save()
    create_voucher(
        token_client, organizer, event,
        data={
            'quota': quota.pk,
            'block_quota': True
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_create_duplicate_code(token_client, organizer, event, quota):
    with scopes_disabled():
        v = event.vouchers.create(quota=quota)
    create_voucher(
        token_client, organizer, event,
        data={
            'quota': quota.pk,
            'code': v.code,
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_subevent_optional(token_client, organizer, event, item, subevent):
    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
        },
    )
    assert v.subevent is None
    assert v.block_quota is False
    assert v.item == item


@pytest.mark.django_db
def test_subevent_required_for_blocking(token_client, organizer, event, item, subevent):
    create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'block_quota': True
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_subevent_blocking_quota_free(token_client, organizer, event, item, quota, subevent):
    with scopes_disabled():
        se2 = event.subevents.create(name="Bar", date_from=now())
        quota.subevent = subevent
        quota.save()
        q2 = event.quotas.create(event=event, name='Tickets', size=0, subevent=se2)
        q2.items.add(item)

    v = create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'block_quota': True,
            'subevent': subevent.pk
        },
    )
    assert v.block_quota
    assert v.subevent == subevent


@pytest.mark.django_db
def test_subevent_blocking_quota_full(token_client, organizer, event, item, quota, subevent):
    with scopes_disabled():
        se2 = event.subevents.create(name="Bar", date_from=now())
        quota.subevent = subevent
        quota.size = 0
        quota.save()
        q2 = event.quotas.create(event=event, name='Tickets', size=5, subevent=se2)
        q2.items.add(item)

    create_voucher(
        token_client, organizer, event,
        data={
            'item': item.pk,
            'block_quota': True,
            'subevent': subevent.pk
        },
        expected_failure=True
    )


def change_voucher(token_client, organizer, event, voucher, data, expected_failure=False):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/vouchers/{}/'.format(organizer.slug, event.slug, voucher.pk),
        data=data, format='json'
    )
    if expected_failure:
        assert resp.status_code == 400
    else:
        assert resp.status_code == 200
    voucher.refresh_from_db()


@pytest.mark.django_db
def test_change_to_item_of_other_event(token_client, organizer, event, item):
    with scopes_disabled():
        e2 = Event.objects.create(
            organizer=organizer,
            name='Dummy2',
            slug='dummy2',
            date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC),
            plugins='pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf'
        )
        ticket2 = e2.items.create(name='Late-bird ticket', default_price=23)
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'item': ticket2.pk
        },
        expected_failure=True
    )
    v.refresh_from_db()
    assert v.item == item


@pytest.mark.django_db
def test_change_non_blocking_voucher(token_client, organizer, event, item, quota):
    with scopes_disabled():
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'quota': quota.pk,
            'item': None
        }
    )
    assert v.item is None
    assert v.quota == quota


@pytest.mark.django_db
def test_change_voucher_reduce_max_usages(token_client, organizer, event, item, quota):
    with scopes_disabled():
        v = event.vouchers.create(item=item, max_usages=5, redeemed=3)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'max_usages': 2
        },
        expected_failure=True
    )
    assert v.max_usages == 5


@pytest.mark.django_db
def test_change_blocking_voucher_unchanged_quota_full(token_client, organizer, event, item, quota):
    quota.size = 0
    quota.save()
    with scopes_disabled():
        v = event.vouchers.create(item=item, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'comment': 'Foo'
        }
    )
    assert v.item == item
    assert v.block_quota
    assert v.comment == 'Foo'


@pytest.mark.django_db
def test_change_voucher_to_blocking_quota_full(token_client, organizer, event, item, quota):
    quota.size = 0
    quota.save()
    with scopes_disabled():
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'block_quota': True
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_change_voucher_to_blocking_quota_free(token_client, organizer, event, item, quota):
    with scopes_disabled():
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'block_quota': True
        },
    )
    assert v.block_quota


@pytest.mark.django_db
def test_change_voucher_validity_to_valid_quota_full(token_client, organizer, event, item, quota):
    quota.size = 0
    quota.save()
    with scopes_disabled():
        v = event.vouchers.create(item=item, valid_until=now() - datetime.timedelta(days=3),
                                  block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'valid_until': (now() + datetime.timedelta(days=3)).isoformat()
        },
        expected_failure=True
    )
    assert v.valid_until < now()


@pytest.mark.django_db
def test_change_voucher_validity_to_valid_quota_free(token_client, organizer, event, item, quota):
    with scopes_disabled():
        v = event.vouchers.create(item=item, valid_until=now() - datetime.timedelta(days=3),
                                  block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'valid_until': (now() + datetime.timedelta(days=3)).isoformat()
        },
    )
    assert v.valid_until > now()


@pytest.mark.django_db
def test_change_item_of_blocking_voucher_quota_free(token_client, organizer, event, item, quota):
    with scopes_disabled():
        ticket2 = event.items.create(name='Late-bird ticket', default_price=23)
        quota.items.add(ticket2)
        v = event.vouchers.create(item=item, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'item': ticket2.pk
        },
    )
    assert v.item == ticket2


@pytest.mark.django_db
def test_change_item_of_blocking_voucher_quota_full(token_client, organizer, event, item, quota):
    with scopes_disabled():
        ticket2 = event.items.create(name='Late-bird ticket', default_price=23)
        quota2 = event.quotas.create(name='Late', size=0)
        quota2.items.add(ticket2)
        v = event.vouchers.create(item=item, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'item': ticket2.pk
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_change_variation_of_blocking_voucher_quota_free(token_client, organizer, event):
    with scopes_disabled():
        shirt = event.items.create(name='Shirt', default_price=23)
        vs = shirt.variations.create(value='S')
        vm = shirt.variations.create(value='M')
        qs = event.quotas.create(name='S', size=2)
        qs.variations.add(vs)
        qm = event.quotas.create(name='M', size=2)
        qm.variations.add(vm)
        v = event.vouchers.create(item=shirt, variation=vs, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'variation': vm.pk
        },
    )
    assert v.variation == vm


@pytest.mark.django_db
def test_change_variation_of_blocking_voucher_without_quota_change(token_client, organizer, event):
    with scopes_disabled():
        shirt = event.items.create(name='Shirt', default_price=23)
        vs = shirt.variations.create(value='S')
        vm = shirt.variations.create(value='M')
        q = event.quotas.create(name='S', size=0)
        q.variations.add(vs)
        q.variations.add(vm)
        v = event.vouchers.create(item=shirt, variation=vs, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'variation': vm.pk
        }
    )
    assert v.variation == vm


@pytest.mark.django_db
def test_change_variation_of_blocking_voucher_quota_full(token_client, organizer, event):
    with scopes_disabled():
        shirt = event.items.create(name='Shirt', default_price=23)
        vs = shirt.variations.create(value='S')
        vm = shirt.variations.create(value='M')
        qs = event.quotas.create(name='S', size=2)
        qs.variations.add(vs)
        qm = event.quotas.create(name='M', size=0)
        qm.variations.add(vm)
        v = event.vouchers.create(item=shirt, variation=vs, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'variation': vm.pk
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_change_quota_of_blocking_voucher_quota_free(token_client, organizer, event):
    with scopes_disabled():
        qs = event.quotas.create(name='S', size=2)
        qm = event.quotas.create(name='M', size=2)
        v = event.vouchers.create(quota=qs, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'quota': qm.pk
        },
    )
    assert v.quota == qm


@pytest.mark.django_db
def test_change_quota_of_blocking_voucher_quota_full(token_client, organizer, event):
    with scopes_disabled():
        qs = event.quotas.create(name='S', size=2)
        qm = event.quotas.create(name='M', size=0)
        v = event.vouchers.create(quota=qs, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'quota': qm.pk
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_change_item_of_blocking_voucher_without_quota_change(token_client, organizer, event, item, quota):
    with scopes_disabled():
        quota.size = 0
        quota.save()
        ticket2 = event.items.create(name='Standard Ticket', default_price=23)
        quota.items.add(ticket2)
        v = event.vouchers.create(item=item, block_quota=True)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'item': ticket2.pk
        },
    )
    assert v.item == ticket2


@pytest.mark.django_db
def test_change_code_to_duplicate(token_client, organizer, event, item, quota):
    with scopes_disabled():
        v1 = event.vouchers.create(quota=quota)
        v2 = event.vouchers.create(quota=quota)
    change_voucher(
        token_client, organizer, event, v1,
        data={
            'code': v2.code
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_change_subevent_blocking_quota_free(token_client, organizer, event, item, quota, subevent):
    with scopes_disabled():
        quota.subevent = subevent
        quota.save()
        se2 = event.subevents.create(name="Bar", date_from=now())
        q2 = event.quotas.create(event=event, name='Tickets', size=5, subevent=se2)
        q2.items.add(item)

        v = event.vouchers.create(item=item, block_quota=True, subevent=subevent)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'subevent': se2.pk
        },
    )
    assert v.subevent == se2


@pytest.mark.django_db
def test_change_subevent_blocking_quota_full(token_client, organizer, event, item, quota, subevent):
    with scopes_disabled():
        quota.subevent = subevent
        quota.save()
        se2 = event.subevents.create(name="Bar", date_from=now())
        q2 = event.quotas.create(event=event, name='Tickets', size=0, subevent=se2)
        q2.items.add(item)

        v = event.vouchers.create(item=item, block_quota=True, subevent=subevent)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'subevent': se2.pk
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_delete_voucher(token_client, organizer, event, quota):
    with scopes_disabled():
        v = event.vouchers.create(quota=quota)
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/vouchers/{}/'.format(organizer.slug, event.slug, v.pk),
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.vouchers.filter(pk=v.id).exists()


@pytest.mark.django_db
def test_delete_voucher_redeemed(token_client, organizer, event, quota):
    with scopes_disabled():
        v = event.vouchers.create(quota=quota, redeemed=1)
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/vouchers/{}/'.format(organizer.slug, event.slug, v.pk),
    )
    assert resp.status_code == 403
    with scopes_disabled():
        assert event.vouchers.filter(pk=v.id).exists()


@pytest.mark.django_db
def test_redeemed_is_not_writable(token_client, organizer, event, item):
    with scopes_disabled():
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'redeemed': 1,
        },
    )
    assert v.redeemed == 0


@pytest.mark.django_db
def test_create_multiple_vouchers(token_client, organizer, event, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/vouchers/batch_create/'.format(organizer.slug, event.slug),
        data=[
            {
                'code': 'ABCDEFGHI',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': False,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None
            },
            {
                'code': 'JKLMNOPQR',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': True,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None
            }
        ], format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert Voucher.objects.count() == 2
        assert resp.data[0]['code'] == 'ABCDEFGHI'
        v1 = Voucher.objects.get(code='ABCDEFGHI')
        assert not v1.block_quota
        assert resp.data[1]['code'] == 'JKLMNOPQR'
        v2 = Voucher.objects.get(code='JKLMNOPQR')
        assert v2.block_quota


@pytest.mark.django_db
def test_create_multiple_vouchers_one_invalid(token_client, organizer, event, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/vouchers/batch_create/'.format(organizer.slug, event.slug),
        data=[
            {
                'code': 'ABCDEFGHI',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': False,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None
            },
            {
                'code': 'J',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': True,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None
            }
        ], format='json'
    )
    assert resp.status_code == 400
    assert resp.data == [{}, {'code': ['Ensure this field has at least 5 characters.']}]
    with scopes_disabled():
        assert Voucher.objects.count() == 0


@pytest.mark.django_db
def test_create_multiple_vouchers_duplicate_code(token_client, organizer, event, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/vouchers/batch_create/'.format(organizer.slug, event.slug),
        data=[
            {
                'code': 'ABCDEFGHI',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': False,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None
            },
            {
                'code': 'ABCDEFGHI',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': True,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None
            }
        ], format='json'
    )
    assert resp.status_code == 400
    assert resp.data == [{}, {'code': ['Duplicate voucher code in request.']}]
    with scopes_disabled():
        assert Voucher.objects.count() == 0


@pytest.fixture
def seatingplan(organizer, event):
    plan = SeatingPlan.objects.create(
        name="Plan", organizer=organizer, layout="{}"
    )
    event.seating_plan = plan
    event.save()
    return plan


@pytest.fixture
def seat1(item, event):
    return event.seats.create(name="A1", product=item, seat_guid="A1")


@pytest.mark.django_db
def test_create_multiple_vouchers_duplicate_seat(token_client, organizer, event, item, seat1, seatingplan):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/vouchers/batch_create/'.format(organizer.slug, event.slug),
        data=[
            {
                'code': 'ABCDEFGHI',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': False,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None,
                'seat': 'A1',
            },
            {
                'code': 'ABCDEFGHI',
                'max_usages': 1,
                'valid_until': None,
                'block_quota': True,
                'allow_ignore_quota': False,
                'price_mode': 'set',
                'value': '12.00',
                'item': item.pk,
                'variation': None,
                'quota': None,
                'tag': 'Foo',
                'comment': '',
                'subevent': None,
                'seat': 'A1',
            }
        ], format='json'
    )
    assert resp.status_code == 400
    assert resp.data == [{}, {'code': ['Duplicate seat ID in request.']}]
    with scopes_disabled():
        assert Voucher.objects.count() == 0


@pytest.mark.django_db
def test_set_seat_ok(token_client, organizer, event, seatingplan, seat1, item):
    with scopes_disabled():
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1'
        },
    )
    with scopes_disabled():
        v.refresh_from_db()
        assert v.seat == seat1


@pytest.mark.django_db
def test_save_set_seat(token_client, organizer, event, seatingplan, seat1, item):
    with scopes_disabled():
        v = event.vouchers.create(item=item, seat=seat1)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1'
        },
    )
    with scopes_disabled():
        v.refresh_from_db()
        assert v.seat == seat1


@pytest.mark.django_db
def test_set_seat_unknown(token_client, organizer, event, seatingplan, seat1, item):
    with scopes_disabled():
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'unknown'
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_seat_seat_productmissing(token_client, organizer, event, seatingplan, seat1, item, quota):
    with scopes_disabled():
        v = event.vouchers.create(quota=quota)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1'
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_seat_seat_productwrong(token_client, organizer, event, seatingplan, seat1, item, quota):
    with scopes_disabled():
        i2 = event.items.create(name="Budget Ticket", default_price=23)
        v = event.vouchers.create(item=i2)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1'
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_seat_seat_usages(token_client, organizer, event, seatingplan, seat1, item, quota):
    with scopes_disabled():
        v = event.vouchers.create(item=item, max_usages=2)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1'
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_seat_seat_duplicate(token_client, organizer, event, seatingplan, seat1, item, quota):
    with scopes_disabled():
        event.vouchers.create(item=item, seat=seat1)
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1'
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_set_seat_subevent(token_client, organizer, event, seatingplan, seat1, item, quota):
    with scopes_disabled():
        event.has_subevents = True
        event.save()
        se1 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
        se2 = event.subevents.create(name="Baz", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
        seat1 = event.seats.create(name="A1", product=item, seat_guid="A1", subevent=se1)
        event.seats.create(name="A1", product=item, seat_guid="A1", subevent=se2)
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1',
            'subevent': se1.pk
        },
    )
    with scopes_disabled():
        v.refresh_from_db()
        assert v.seat == seat1
        assert v.subevent == se1


@pytest.mark.django_db
def test_set_seat_subevent_required(token_client, organizer, event, seatingplan, seat1, item, quota):
    with scopes_disabled():
        event.has_subevents = True
        event.save()
        se1 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
        se2 = event.subevents.create(name="Baz", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
        seat1 = event.seats.create(name="A1", product=item, seat_guid="A1", subevent=se1)
        event.seats.create(name="A1", product=item, seat_guid="A1", subevent=se2)
        event.vouchers.create(item=item, seat=seat1)
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1',
        },
        expected_failure=True
    )


@pytest.mark.django_db
def test_set_seat_subevent_invalid(token_client, organizer, event, seatingplan, seat1, item, quota):
    with scopes_disabled():
        event.has_subevents = True
        event.save()
        se1 = event.subevents.create(name="Foobar", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
        se2 = event.subevents.create(name="Baz", date_from=datetime.datetime(2017, 12, 27, 10, 0, 0, tzinfo=UTC))
        seat1 = event.seats.create(name="A1", product=item, seat_guid="A1", subevent=se1)
        event.seats.create(name="B1", product=item, seat_guid="B1", subevent=se2)
        event.vouchers.create(item=item, seat=seat1, subevent=se2)
        v = event.vouchers.create(item=item)
    change_voucher(
        token_client, organizer, event, v,
        data={
            'seat': 'A1',
        },
        expected_failure=True
    )
