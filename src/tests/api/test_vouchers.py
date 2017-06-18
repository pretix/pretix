import datetime

import pytest
from django.utils import timezone


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
    'comment': ''
}


@pytest.mark.django_db
def test_voucher_list(token_client, organizer, event, voucher, item, quota):
    res = dict(TEST_VOUCHER_RES)
    res['item'] = item.pk
    res['id'] = voucher.pk
    res['code'] = voucher.code

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
        '/api/v1/organizers/{}/events/{}/vouchers/?item={}'.format(organizer.slug, event.slug, item.pk + 1)
    )
    assert [] == resp.data['results']

    var = item.variations.create(value='VIP')
    voucher.variation = var
    voucher.save()
    res['variation'] = var.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?variation={}'.format(organizer.slug, event.slug, var.pk)
    )
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/vouchers/?variation={}'.format(organizer.slug, event.slug, var.pk + 1)
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
        '/api/v1/organizers/{}/events/{}/vouchers/?quota={}'.format(organizer.slug, event.slug, quota.pk + 1)
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
