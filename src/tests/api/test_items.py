from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django_countries.fields import Country
from pytz import UTC

from pretix.base.models import InvoiceAddress, Order, OrderPosition, CartPosition, Quota, ItemVariation, ItemAddOn
from pretix.base.models.orders import OrderFee


@pytest.fixture
def category(event):
    return event.categories.create(name="Tickets")


@pytest.fixture
def category2(event2):
    return event2.categories.create(name="Tickets2")


@pytest.fixture
def order(event, item, taxrule):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC),
            expires=datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC),
            total=23, payment_provider='banktransfer', locale='en'
        )
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule)
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        return o


@pytest.fixture
def order_position(item, order, taxrule, variation):
    op = OrderPosition.objects.create(
        order=order,
        item=item,
        variation=variation,
        tax_rule=taxrule,
        tax_rate=taxrule.rate,
        tax_value=Decimal("3"),
        price=Decimal("23"),
        attendee_name="Peter",
        secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
    )
    return op


@pytest.fixture
def cart_position(event, item, variation):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        c = CartPosition.objects.create(
            event=event,
            item=item,
            datetime=datetime.now(),
            expires=datetime.now() + timedelta(days=1),
            variation=variation,
            price=Decimal("23"),
            cart_id="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
        )
        return c


TEST_CATEGORY_RES = {
    "name": {"en": "Tickets"},
    "description": {"en": ""},
    "position": 0,
    "is_addon": False
}


@pytest.mark.django_db
def test_category_list(token_client, organizer, event, team, category):
    res = dict(TEST_CATEGORY_RES)
    res["id"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/?is_addon=false'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/?is_addon=true'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    category.is_addon = True
    category.save()
    res["is_addon"] = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/?is_addon=true'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_category_detail(token_client, organizer, event, team, category):
    res = dict(TEST_CATEGORY_RES)
    res["id"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event.slug,
                                                                                    category.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item2(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item3(event):
    return event.items.create(name="Budget Ticket", default_price=23)


TEST_ITEM_RES = {
    "name": {"en": "Budget Ticket"},
    "default_price": "23.00",
    "category": None,
    "active": True,
    "description": None,
    "free_price": False,
    "tax_rate": "0.00",
    "tax_rule": None,
    "admission": False,
    "position": 0,
    "picture": None,
    "available_from": None,
    "available_until": None,
    "require_voucher": False,
    "hide_without_voucher": False,
    "allow_cancel": True,
    "min_per_order": None,
    "max_per_order": None,
    "checkin_attention": False,
    "has_variations": False,
    "variations": [],
    "addons": []
}


@pytest.mark.django_db
def test_item_list(token_client, organizer, event, team, item):
    res = dict(TEST_ITEM_RES)
    res["id"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?active=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?active=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?category=1'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    item.admission = True
    item.save()
    res['admission'] = True

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?tax_rate=0'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?tax_rate=19'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?free_price=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_item_detail(token_client, organizer, event, team, item):
    res = dict(TEST_ITEM_RES)
    res["id"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_item_detail_variations(token_client, organizer, event, team, item):
    var = item.variations.create(value="Children")
    res = dict(TEST_ITEM_RES)
    res["id"] = item.pk
    res["variations"] = [{
        "id": var.pk,
        "value": {"en": "Children"},
        "default_price": None,
        "price": Decimal("23.00"),
        "active": True,
        "description": None,
        "position": 0,
    }]
    res["has_variations"] = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res['variations'] == resp.data['variations']


@pytest.mark.django_db
def test_item_detail_addons(token_client, organizer, event, team, item, category):
    item.addons.create(addon_category=category)
    res = dict(TEST_ITEM_RES)

    res["id"] = item.pk
    res["addons"] = [{
        "addon_category": category.pk,
        "min_count": 0,
        "max_count": 1,
        "position": 0,
        "price_included": False
    }]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_item_create(token_client, organizer, event, item, category, taxrule):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "has_variations": True
        },
        format='json'
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_item_update(token_client, organizer, event, item, category2, taxrule2):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "min_per_order": 10,
            "max_per_order": 2
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["max_per_order must be greater than min_per_order (or null for no limitation)."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "available_from": "2017-12-30T12:00",
            "available_until": "2017-12-29T12:00"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The available_from date must be before the available_until date (or null)."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "category": category2.pk
        },
        format='json'

    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The items category must belong to the same event as the item."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "tax_rule": taxrule2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The items tax_rule must belong to the same event as the item."]}'


@pytest.mark.django_db
def test_items_delete(token_client, organizer, event, item):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 204
    assert not event.items.filter(pk=item.id).exists()


@pytest.mark.django_db
def test_items_with_order_position_not_delete(token_client, organizer, event, item, order_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 403
    assert event.items.filter(pk=item.id).exists()


@pytest.mark.django_db
def test_items_with_cart_position_not_delete(token_client, organizer, event, item, cart_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 403
    assert event.items.filter(pk=item.id).exists()


@pytest.fixture
def variations(item):
    v = list()
    v.append(item.variations.create(value="ChildA1"))
    v.append(item.variations.create(value="ChildA2"))
    return v


@pytest.fixture
def variations2(item2):
    v = list()
    v.append(item2.variations.create(value="ChildB1"))
    v.append(item2.variations.create(value="ChildB2"))
    return v


@pytest.fixture
def variation(item):
    return item.variations.create(value="ChildC1")


TEST_VARIATIONS_RES = {
    "value": {
        "en": "ChildC1"
    },
    "active": True,
    "description": None,
    "position": 0,
    "default_price": None,
    "price": 23.0
}

TEST_VARIATIONS_UPDATE = {
    "value": {
        "en": "ChildC2"
    },
    "active": True,
    "description": None,
    "position": 1,
    "default_price": None,
    "price": 23.0
}


@pytest.mark.django_db
def test_variations_list(token_client, organizer, event, item, variation):
    res = dict(TEST_VARIATIONS_RES)
    res["id"] = variation.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/variations/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 200
    assert res['value'] == resp.data['results'][0]['value']
    assert res['position'] == resp.data['results'][0]['position']
    assert res['price'] == resp.data['results'][0]['price']


@pytest.mark.django_db
def test_variations_detail(token_client, organizer, event, item, variation):
    res = dict(TEST_VARIATIONS_RES)
    res["id"] = variation.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_variations_create(token_client, organizer, event, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/'.format(organizer.slug, event.slug, item.pk),
        {
            "value": {
                "en": "ChildC2"
            },
            "active": True,
            "description": None,
            "position": 1,
            "default_price": None,
            "price": 23.0
        },
        format='json'
    )
    assert resp.status_code == 201
    var = ItemVariation.objects.get(pk=resp.data['id'])
    assert var.position == 1
    assert var.price == 23.0


@pytest.mark.django_db
def test_variations_update(token_client, organizer, event, item, item3, variation):
    res = dict(TEST_VARIATIONS_UPDATE)
    res["id"] = variation.pk
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk),
        {
            "value": {
                "en": "ChildC2"
            },
            "position": 1
        },
        format='json'
    )
    assert resp.status_code == 200
    assert res == resp.data

    # Variation exists but do not belong to item
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item3.pk, variation.pk),
        {
            "position": 1
        },
        format='json'
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_variations_delete(token_client, organizer, event, item, variation, order):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk))
    assert resp.status_code == 204
    assert not item.variations.filter(pk=variation.id).exists()


@pytest.mark.django_db
def test_variations_with_order_position_not_delete(token_client, organizer, event, item, order, variation, order_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk))
    assert resp.status_code == 403
    assert item.variations.filter(pk=variation.id).exists()


@pytest.mark.django_db
def test_variations_with_cart_position_not_delete(token_client, organizer, event, item, variation, cart_position):
    assert item.variations.filter(pk=variation.id).exists()
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk))
    assert resp.status_code == 403
    assert item.variations.filter(pk=variation.id).exists()


@pytest.fixture
def addon(item, category):
    return item.addons.create(addon_category=category, min_count=0, max_count=10, position=1)


TEST_ADDONS_RES = {
    "min_count": 0,
    "max_count": 10,
    "position": 1,
    "price_included": False
}


@pytest.mark.django_db
def test_addons_list(token_client, organizer, event, item, addon, category):
    res = dict(TEST_ADDONS_RES)
    res["id"] = addon.pk
    res["addon_category"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 200
    assert res['addon_category'] == resp.data['results'][0]['addon_category']
    assert res['min_count'] == resp.data['results'][0]['min_count']
    assert res['max_count'] == resp.data['results'][0]['max_count']
    assert res['position'] == resp.data['results'][0]['position']


@pytest.mark.django_db
def test_addons_detail(token_client, organizer, event, item, addon, category):
    res = dict(TEST_ADDONS_RES)
    res["id"] = addon.pk
    res["addon_category"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug, item.pk, addon.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_addons_create(token_client, organizer, event, item, category, category2):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug, item.pk),
        {
            "addon_category": category.pk,
            "min_count": 0,
            "max_count": 10,
            "position": 1,
            "price_included": False
        },
        format='json'
    )
    assert resp.status_code == 201
    addon = ItemAddOn.objects.get(pk=resp.data['id'])
    assert addon.position == 1
    assert addon.addon_category == category

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug, item.pk),
        {
            "addon_category": category.pk,
            "min_count": 10,
            "max_count": 20,
            "position": 2,
            "price_included": False
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The item all ready have an add-on of this category."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug, item.pk),
        {
            "addon_category": category2.pk,
            "min_count": 10,
            "max_count": 20,
            "position": 2,
            "price_included": False
        },
        format='json'
    )
    assert resp.status_code == 201
    addon = ItemAddOn.objects.get(pk=resp.data['id'])
    assert addon.position == 2
    assert addon.addon_category == category2


@pytest.mark.django_db
def test_addons_update(token_client, organizer, event, item, addon):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug, item.pk, addon.pk),
        {
            "min_count": 100,
            "max_count": 101
        },
        format='json'
    )
    assert resp.status_code == 200
    a = ItemAddOn.objects.get(pk=addon.pk)
    assert a.min_count == 100
    assert a.max_count == 101

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug, item.pk, a.pk),
        {
            "min_count": 10,
            "max_count": 1
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The minimum number needs to be lower than the maximum number."]}'


@pytest.mark.django_db
def test_addons_delete(token_client, organizer, event, item, addon):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug, item.pk, addon.pk))
    assert resp.status_code == 204
    assert not item.addons.filter(pk=addon.id).exists()


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(item)
    return q


TEST_QUOTA_RES = {
    "name": "Budget Quota",
    "size": 200,
    "items": [],
    "variations": [],
    "subevent": None
}


@pytest.mark.django_db
def test_quota_list(token_client, organizer, event, quota, item, subevent):
    res = dict(TEST_QUOTA_RES)
    res["id"] = quota.pk
    res["items"] = [item.pk]

    resp = token_client.get('/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    quota.subevent = subevent
    quota.save()
    res["subevent"] = subevent.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/quotas/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/quotas/?subevent={}'.format(organizer.slug, event.slug, subevent.pk + 1))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_quota_detail(token_client, organizer, event, quota, item):
    res = dict(TEST_QUOTA_RES)

    res["id"] = quota.pk
    res["items"] = [item.pk]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug,
                                                                                quota.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_quota_create(token_client, organizer, event, event2, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 201
    quota = Quota.objects.get(pk=resp.data['id'])
    assert quota.name == "Ticket Quota"
    assert quota.size == 200

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event2.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more items do not belong to this event."]}'


@pytest.mark.django_db
def test_quota_create_with_variations(token_client, organizer, event, item, variations, variations2):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 201

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [100],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"variations":["Invalid pk \\"100\\" - object does not exist."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk, variations2[0].pk],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["All variations must belong to an item contained in the items list."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more items has variations but none of these are in the variations list."]}'


@pytest.mark.django_db
def test_quota_create_with_subevent(token_client, organizer, event, event3, item, variations, subevent, subevent2):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": subevent.pk
        },
        format='json'
    )
    assert resp.status_code == 201

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Subevent cannot be null for event series."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": subevent2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The subevent does not belong to this event."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event3.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [],
            "variations": [],
            "subevent": subevent2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The subevent does not belong to this event."]}'


@pytest.mark.django_db
def test_quota_update(token_client, organizer, event, quota, item):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug, quota.pk),
        {
            "name": "Ticket Quota Update",
            "size": 111,
        },
        format='json'
    )
    assert resp.status_code == 200
    quota = Quota.objects.get(pk=resp.data['id'])
    assert quota.name == "Ticket Quota Update"
    assert quota.size == 111


@pytest.mark.django_db
def test_quota_delete(token_client, organizer, event, quota):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug, quota.pk))
    assert resp.status_code == 204
    assert not event.quotas.filter(pk=quota.id).exists()


@pytest.mark.django_db
def test_quota_availability(token_client, organizer, event, quota, item):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/quotas/{}/availability/'.format(
        organizer.slug, event.slug, quota.pk))
    assert resp.status_code == 200
    assert {'blocking_vouchers': 0,
            'available_number': 200,
            'pending_orders': 0,
            'cart_positions': 0,
            'available': True,
            'total_size': 200,
            'paid_orders': 0,
            'waiting_list': 0} == resp.data


@pytest.fixture
def question(event, item):
    q = event.questions.create(question="T-Shirt size", type="C")
    q.items.add(item)
    q.options.create(answer="XL")
    return q


TEST_QUESTION_RES = {
    "question": {"en": "T-Shirt size"},
    "type": "C",
    "required": False,
    "items": [],
    "position": 0,
    "options": [
        {
            "id": 0,
            "answer": {"en": "XL"}
        }
    ]
}


@pytest.mark.django_db
def test_question_list(token_client, organizer, event, question, item):
    res = dict(TEST_QUESTION_RES)
    res["id"] = question.pk
    res["items"] = [item.pk]
    res["options"][0]["id"] = question.options.first().pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_question_detail(token_client, organizer, event, question, item):
    res = dict(TEST_QUESTION_RES)

    res["id"] = question.pk
    res["items"] = [item.pk]
    res["options"][0]["id"] = question.options.first().pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug,
                                                                                   question.pk))
    assert resp.status_code == 200
    assert res == resp.data
