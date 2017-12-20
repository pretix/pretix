import datetime
import time
from decimal import Decimal
from unittest import mock

import pytest
from django_countries.fields import Country
from pytz import UTC

from pretix.base.models import (
    CheckinList, InvoiceAddress, Order, OrderPosition,
)


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item_on_wrong_event(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def other_item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def order(event, item, other_item, taxrule):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PAID, secret="k24fiuwvu8kxz3y1",
            datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=UTC),
            expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=UTC),
            total=46, payment_provider='banktransfer', locale='en'
        )
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        OrderPosition.objects.create(
            order=o,
            positionid=1,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name="Peter",
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
        )
        OrderPosition.objects.create(
            order=o,
            positionid=2,
            item=other_item,
            variation=None,
            price=Decimal("23"),
            attendee_name="Michael",
            secret="sf4HZG73fU6kwddgjg2QOusFbYZwVKpK"
        )
        return o


TEST_ORDERPOSITION1_RES = {
    "id": 1,
    "order": "FOO",
    "positionid": 1,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name": "Peter",
    "attendee_email": None,
    "voucher": None,
    "tax_rate": "0.00",
    "tax_value": "0.00",
    "tax_rule": None,
    "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
    "addon_to": None,
    "checkins": [],
    "downloads": [],
    "answers": [],
    "subevent": None
}


TEST_ORDERPOSITION2_RES = {
    "id": 2,
    "order": "FOO",
    "positionid": 2,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name": "Michael",
    "attendee_email": None,
    "voucher": None,
    "tax_rate": "0.00",
    "tax_value": "0.00",
    "tax_rule": None,
    "secret": "sf4HZG73fU6kwddgjg2QOusFbYZwVKpK",
    "addon_to": None,
    "checkins": [],
    "downloads": [],
    "answers": [],
    "subevent": None
}

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


@pytest.fixture
def clist_all(event, item):
    c = event.checkin_lists.create(name="Default", all_products=True)
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


@pytest.mark.django_db
def test_list_all_items_positions(token_client, organizer, event, clist, clist_all, item, other_item, order):
    p1 = dict(TEST_ORDERPOSITION1_RES)
    p1["id"] = order.positions.first().pk
    p1["item"] = item.pk
    p2 = dict(TEST_ORDERPOSITION2_RES)
    p2["id"] = order.positions.last().pk
    p2["item"] = other_item.pk

    # All items
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=positionid'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p1, p2] == resp.data['results']

    # Check-ins on other list ignored
    order.positions.first().checkins.create(list=clist)
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=positionid'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p1, p2] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?has_checkin=1'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    # Only checked in
    c = order.positions.first().checkins.create(list=clist_all)
    p1['checkins'] = [
        {
            'list': clist_all.pk,
            'datetime': c.datetime.isoformat().replace('+00:00', 'Z')
        }
    ]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?has_checkin=1'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p1] == resp.data['results']

    # Only not checked in
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?has_checkin=0'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p2] == resp.data['results']

    # Order by checkin
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=-last_checked_in'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p1, p2] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=last_checked_in'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p2, p1] == resp.data['results']

    # Order by checkin date
    time.sleep(1)
    c = order.positions.last().checkins.create(list=clist_all)
    p2['checkins'] = [
        {
            'list': clist_all.pk,
            'datetime': c.datetime.isoformat().replace('+00:00', 'Z')
        }
    ]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=-last_checked_in'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p2, p1] == resp.data['results']

    # Order by attendee_name
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=-attendee_name'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p1, p2] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=attendee_name'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [p2, p1] == resp.data['results']

    # Paid only
    order.status = Order.STATUS_PENDING
    order.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/'.format(
        organizer.slug, event.slug, clist_all.pk
    ))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_list_limited_items_positions(token_client, organizer, event, clist, item, order):
    p1 = dict(TEST_ORDERPOSITION1_RES)
    p1["id"] = order.positions.first().pk
    p1["item"] = item.pk

    # All items
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/?ordering=positionid'.format(
        organizer.slug, event.slug, clist.pk
    ))
    assert resp.status_code == 200
    assert [p1] == resp.data['results']


@pytest.mark.django_db
def test_list_limited_items_position_detail(token_client, organizer, event, clist, item, order):
    p1 = dict(TEST_ORDERPOSITION1_RES)
    p1["id"] = order.positions.first().pk
    p1["item"] = item.pk

    # All items
    resp = token_client.get('/api/v1/organizers/{}/events/{}/checkinlists/{}/positions/{}/'.format(
        organizer.slug, event.slug, clist.pk, order.positions.first().pk
    ))
    assert resp.status_code == 200
    assert p1 == resp.data
