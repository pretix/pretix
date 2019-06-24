from datetime import datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.conf import settings
from django_countries.fields import Country
from django_scopes import scopes_disabled
from pytz import UTC

from pretix.base.models import (
    Event, InvoiceAddress, Order, OrderPosition, SeatingPlan,
)
from pretix.base.models.orders import OrderFee


@pytest.fixture
def variations(item):
    v = list()
    v.append(item.variations.create(value="ChildA1"))
    v.append(item.variations.create(value="ChildA2"))
    return v


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
            total=23, locale='en'
        )
        o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                      tax_value=Decimal('0.05'), tax_rule=taxrule)
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        return o


@pytest.fixture
def order_position(item, order, taxrule, variations):
    op = OrderPosition.objects.create(
        order=order,
        item=item,
        variation=variations[0],
        tax_rule=taxrule,
        tax_rate=taxrule.rate,
        tax_value=Decimal("3"),
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Peter"},
        secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
    )
    return op


TEST_EVENT_RES = {
    "name": {"en": "Dummy"},
    "live": False,
    "testmode": False,
    "currency": "EUR",
    "date_from": "2017-12-27T10:00:00Z",
    "date_to": None,
    "date_admission": None,
    "is_public": True,
    "presale_start": None,
    "presale_end": None,
    "location": None,
    "slug": "dummy",
    "has_subevents": False,
    "seating_plan": None,
    "seat_category_mapping": {},
    "meta_data": {"type": "Conference"},
    'plugins': [
        'pretix.plugins.banktransfer',
        'pretix.plugins.ticketoutputpdf'
    ]
}


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def free_item(event):
    return event.items.create(name="Free Ticket", default_price=0)


@pytest.fixture
def free_quota(event, free_item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(free_item)
    return q


@pytest.mark.django_db
def test_event_list(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug))
    assert resp.status_code == 200
    assert TEST_EVENT_RES == resp.data['results'][0]

    resp = token_client.get('/api/v1/organizers/{}/events/?live=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?live=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?is_public=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?is_public=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?has_subevents=true'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?has_subevents=false'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/?ends_after=2017-12-27T10:01:00Z'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/?ends_after=2017-12-27T09:59:59Z'.format(organizer.slug))
    assert resp.status_code == 200
    assert [TEST_EVENT_RES] == resp.data['results']


@pytest.mark.django_db
def test_event_get(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert TEST_EVENT_RES == resp.data


@pytest.mark.django_db
def test_event_create(token_client, organizer, event, meta_prop):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "meta_data": {
                meta_prop.name: "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        assert not organizer.events.get(slug="2030").testmode
        assert organizer.events.get(slug="2030").meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()
        assert organizer.events.get(slug="2030").plugins == settings.PRETIX_PLUGINS_DEFAULT

    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2020",
            "meta_data": {
                "foo": "bar"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Meta data property \'foo\' does not exist."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": event.slug,
            "meta_data": {
                "type": "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"slug":["This slug has already been used for a different event."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": True,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2031",
            "meta_data": {
                "type": "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"live":["Events cannot be created as \'live\'. Quotas and payment must be added ' \
                                    'to the event before sales can go live."]}'


@pytest.mark.django_db
def test_event_create_with_clone(token_client, organizer, event, meta_prop):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "testmode": True,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "meta_data": {
                "type": "Conference"
            },
            "plugins": [
                "pretix.plugins.ticketoutputpdf"
            ]
        },
        format='json'
    )

    assert resp.status_code == 201
    with scopes_disabled():
        cloned_event = Event.objects.get(organizer=organizer.pk, slug='2030')
        assert cloned_event.plugins == 'pretix.plugins.ticketoutputpdf'
        assert cloned_event.is_public is False
        assert cloned_event.testmode
        assert organizer.events.get(slug="2030").meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2031",
            "meta_data": {
                "type": "Conference"
            }
        },
        format='json'
    )

    assert resp.status_code == 201
    with scopes_disabled():
        cloned_event = Event.objects.get(organizer=organizer.pk, slug='2031')
        assert cloned_event.plugins == "pretix.plugins.banktransfer,pretix.plugins.ticketoutputpdf"
        assert cloned_event.is_public is True
        assert organizer.events.get(slug="2031").meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "date_admission": None,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2032",
            "plugins": []
        },
        format='json'
    )

    assert resp.status_code == 201
    with scopes_disabled():
        cloned_event = Event.objects.get(organizer=organizer.pk, slug='2032')
        assert cloned_event.plugins == ""


@pytest.mark.django_db
def test_event_put_with_clone(token_client, organizer, event, meta_prop):
    resp = token_client.put(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {},
        format='json'
    )

    assert resp.status_code == 405


@pytest.mark.django_db
def test_event_patch_with_clone(token_client, organizer, event, meta_prop):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {},
        format='json'
    )

    assert resp.status_code == 405


@pytest.mark.django_db
def test_event_delete_with_clone(token_client, organizer, event, meta_prop):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/clone/'.format(organizer.slug, event.slug),
        {},
        format='json'
    )

    assert resp.status_code == 405


@pytest.mark.django_db
def test_event_update(token_client, organizer, event, item, meta_prop):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "date_from": "2018-12-27T10:00:00Z",
            "date_to": "2018-12-28T10:00:00Z",
            "currency": "DKK",
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        event = Event.objects.get(organizer=organizer.pk, slug=resp.data['slug'])
        assert event.currency == "DKK"
        assert organizer.events.get(slug=resp.data['slug']).meta_values.filter(
            property__name=meta_prop.name, value="Conference"
        ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-26T10:00:00Z"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The event cannot end before it starts."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "presale_start": "2017-12-27T10:00:00Z",
            "presale_end": "2017-12-26T10:00:00Z"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The event\'s presale cannot end before it starts."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "slug": "testing"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"slug":["The event slug cannot be changed."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "has_subevents": True
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"has_subevents":["Once created an event cannot change between an series and a ' \
                                    'single event."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "meta_data": {
                meta_prop.name: "Workshop"
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert organizer.events.get(slug=resp.data['slug']).meta_values.filter(
            property__name=meta_prop.name, value="Workshop"
        ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "meta_data": {
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert not organizer.events.get(slug=resp.data['slug']).meta_values.filter(
            property__name=meta_prop.name
        ).exists()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "meta_data": {
                "test": "test"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Meta data property \'test\' does not exist."]}'


@pytest.mark.django_db
def test_event_test_mode(token_client, organizer, event):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "testmode": True
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.testmode
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "testmode": False
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert not event.testmode


@pytest.mark.django_db
def test_event_update_live_no_product(token_client, organizer, event):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "live": True
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"live":["You need to configure at least one quota to sell anything."]}'


@pytest.mark.django_db
def test_event_update_live_no_payment_method(token_client, organizer, event, item, free_quota):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "live": True
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"live":["You have configured at least one paid product but have not enabled any ' \
                                    'payment methods."]}'


@pytest.mark.django_db
def test_event_update_live_free_product(token_client, organizer, event, free_item, free_quota):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "live": True
        },
        format='json'
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_event_update_plugins(token_client, organizer, event, free_item, free_quota):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": [
                "pretix.plugins.ticketoutputpdf",
                "pretix.plugins.pretixdroid"
            ]
        },
        format='json'
    )
    assert resp.status_code == 200
    assert set(resp.data.get('plugins')) == {
        "pretix.plugins.ticketoutputpdf",
        "pretix.plugins.pretixdroid"
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": {
                "pretix.plugins.banktransfer"
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data.get('plugins') == [
        "pretix.plugins.banktransfer"
    ]

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": {
                "pretix.plugins.test"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"plugins":["Unknown plugin: \'pretix.plugins.test\'."]}'


@pytest.mark.django_db
def test_event_detail(token_client, organizer, event, team):
    team.all_events = True
    team.save()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert TEST_EVENT_RES == resp.data


@pytest.mark.django_db
def test_event_delete(token_client, organizer, event):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not organizer.events.filter(pk=event.id).exists()


@pytest.mark.django_db
def test_event_with_order_position_not_delete(token_client, organizer, event, item, order_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug))
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"The event can not be deleted as it already contains orders. Please ' \
                                    'set \'live\' to false to hide the event and take the shop offline instead."}'
    with scopes_disabled():
        assert organizer.events.filter(pk=event.id).exists()


@pytest.fixture
def seatingplan(event, organizer, item):
    return SeatingPlan.objects.create(
        name="Plan", organizer=organizer, layout="""{
  "name": "Grosser Saal",
  "categories": [
    {
      "name": "Stalls",
      "color": "red"
    }
  ],
  "zones": [
    {
      "name": "Main Area",
      "position": {
        "x": 0,
        "y": 0
      },
      "rows": [
        {
          "row_number": "0",
          "seats": [
            {
              "seat_guid": "0-0",
              "seat_number": "0-0",
              "position": {
                "x": 0,
                "y": 0
              },
              "category": "Stalls"
            },
            {
              "seat_guid": "0-1",
              "seat_number": "0-1",
              "position": {
                "x": 33,
                "y": 0
              },
              "category": "Stalls"
            },
            {
              "seat_guid": "0-2",
              "seat_number": "0-2",
              "position": {
                "x": 66,
                "y": 0
              },
              "category": "Stalls"
            }
          ],
          "position": {
            "x": 0,
            "y": 0
          }
        }
      ]
    }
  ],
  "size": {
    "width": 600,
    "height": 400
  }
}"""
    )


@pytest.mark.django_db
def test_event_update_seating(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seats.filter(product=item).count() == 3
        m = event.seat_category_mappings.get()
    assert m.layout_category == 'Stalls'
    assert m.product == item


@pytest.mark.django_db
def test_event_update_seating_invalid_product(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk + 2
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"seat_category_mapping":["Item \'3\' does not exist."]}'


@pytest.mark.django_db
def test_event_update_seating_change_mapping(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seats.filter(product=item).count() == 3
        m = event.seat_category_mappings.get()
    assert m.layout_category == 'Stalls'
    assert m.product == item

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seat_category_mapping": {
                "VIP": item.pk,
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        m = event.seat_category_mappings.get()
        assert event.seats.filter(product=None).count() == 3
    assert m.layout_category == 'VIP'
    assert m.product == item


@pytest.mark.django_db
def test_remove_seating(token_client, organizer, event, item, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seat_category_mappings.count() == 1

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": None
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan is None
    with scopes_disabled():
        assert event.seats.count() == 0
        assert event.seat_category_mappings.count() == 0


@pytest.mark.django_db
def test_remove_seating_forbidden(token_client, organizer, event, item, seatingplan, order_position):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    event.refresh_from_db()
    assert event.seating_plan == seatingplan
    with scopes_disabled():
        assert event.seats.count() == 3
        assert event.seat_category_mappings.count() == 1

        order_position.seat = event.seats.first()
        order_position.save()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"seating_plan":["You can not change the plan since seat \\"0-0\\" is not ' \
                                    'present in the new plan and is already sold."]}'


@pytest.mark.django_db
def test_no_seating_for_series(token_client, organizer, event, item, seatingplan, order_position):
    event.has_subevents = True
    event.save()
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Stalls": item.pk
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Event series should not directly be assigned a seating plan."]}'


@pytest.mark.django_db
def test_event_create_with_seating(token_client, organizer, event, meta_prop, seatingplan):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "seating_plan": seatingplan.pk,
            "meta_data": {
                meta_prop.name: "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        event = Event.objects.last()
        assert event.seating_plan == seatingplan
        assert event.seats.count() == 3
        assert event.seat_category_mappings.count() == 0


@pytest.mark.django_db
def test_event_create_with_seating_maps(token_client, organizer, event, meta_prop, seatingplan):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/'.format(organizer.slug),
        {
            "name": {
                "de": "Demo Konference 2020 Test",
                "en": "Demo Conference 2020 Test"
            },
            "live": False,
            "currency": "EUR",
            "date_from": "2017-12-27T10:00:00Z",
            "date_to": "2017-12-28T10:00:00Z",
            "date_admission": None,
            "is_public": False,
            "presale_start": None,
            "presale_end": None,
            "location": None,
            "slug": "2030",
            "seating_plan": seatingplan.pk,
            "seat_category_mapping": {
                "Foo": 1,
            },
            "meta_data": {
                meta_prop.name: "Conference"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"seat_category_mapping":["You cannot specify seat category mappings on event creation."]}'
