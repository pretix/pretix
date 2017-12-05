import pytest

from pretix.base.models import CheckinList


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item_on_wrong_event(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def other_item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


TEST_LIST_RES = {
    "name": "Default",
    "all_products": False,
    "limit_products": [],
    "position_count": 0,
    "checkin_count": 0,
    "subevent": None
}


@pytest.fixture
def clist(event, item):
    c = event.checkin_lists.create(name="Default", all_products=False)
    c.limit_products.add(item)
    return c


@pytest.mark.django_db
def test_list_list(token_client, organizer, event, clist, item, subevent):
    res = dict(TEST_LIST_RES)
    res["id"] = clist.pk
    res["limit_products"] = [item.pk]

    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    clist.subevent = subevent
    clist.save()
    res["subevent"] = subevent.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/checkinlists/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/checkinlists/?subevent={}'.format(organizer.slug, event.slug, subevent.pk + 1))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_list_detail(token_client, organizer, event, clist, item):
    res = dict(TEST_LIST_RES)

    res["id"] = clist.pk
    res["limit_products"] = [item.pk]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/'.format(organizer.slug, event.slug,
                                                                                      clist.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_list_create(token_client, organizer, event, item, item_on_wrong_event):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/checkinlists/'.format(organizer.slug, event.slug),
        {
            "name": "VIP",
            "limit_products": [item.pk],
            "all_products": False,
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 201
    cl = CheckinList.objects.get(pk=resp.data['id'])
    assert cl.name == "VIP"
    assert cl.limit_products.count() == 1
    assert not cl.all_products

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/checkinlists/'.format(organizer.slug, event.slug),
        {
            "name": "VIP",
            "limit_products": [item_on_wrong_event.pk],
            "all_products": True,
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more items do not belong to this event."]}'


@pytest.mark.django_db
def test_list_create_with_subevent(token_client, organizer, event, event3, item, subevent, subevent2):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/checkinlists/'.format(organizer.slug, event.slug),
        {
            "name": "VIP",
            "limit_products": [item.pk],
            "all_products": True,
            "subevent": subevent.pk
        },
        format='json'
    )
    assert resp.status_code == 201

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/checkinlists/'.format(organizer.slug, event.slug),
        {
            "name": "VIP",
            "limit_products": [item.pk],
            "all_products": True,
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Subevent cannot be null for event series."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/checkinlists/'.format(organizer.slug, event.slug),
        {
            "name": "VIP",
            "limit_products": [],
            "all_products": True,
            "subevent": subevent2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The subevent does not belong to this event."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/checkinlists/'.format(organizer.slug, event3.slug),
        {
            "name": "VIP",
            "limit_products": [],
            "all_products": True,
            "subevent": subevent2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The subevent does not belong to this event."]}'


@pytest.mark.django_db
def test_list_update(token_client, organizer, event, clist):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/checkinlists/{}/'.format(organizer.slug, event.slug, clist.pk),
        {
            "name": "VIP",
        },
        format='json'
    )
    assert resp.status_code == 200
    cl = CheckinList.objects.get(pk=resp.data['id'])
    assert cl.name == "VIP"
