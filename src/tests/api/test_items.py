from decimal import Decimal

import pytest


@pytest.fixture
def category(event):
    return event.categories.create(name="Tickets")


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
        "position": 0
    }]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res == resp.data


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
