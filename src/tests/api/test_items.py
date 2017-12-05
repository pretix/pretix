from decimal import Decimal

import pytest

from pretix.base.models import Quota


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
