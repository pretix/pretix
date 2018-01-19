import pytest

from pretix.base.models import Event

TEST_EVENT_RES = {
    "name": {"en": "Dummy"},
    "live": False,
    "currency": "EUR",
    "date_from": "2017-12-27T10:00:00Z",
    "date_to": None,
    "date_admission": None,
    "is_public": False,
    "presale_start": None,
    "presale_end": None,
    "location": None,
    "slug": "dummy",
    "has_subevents": False,
    "meta_data": {"type": "Conference"},
    'plugins': {
        'pretix.plugins.banktransfer': True,
        'pretix.plugins.paypal': False,
        'pretix.plugins.pretixdroid': False,
        'pretix.plugins.reports': False,
        'pretix.plugins.sendmail': False,
        'pretix.plugins.statistics': False,
        'pretix.plugins.stripe': False,
        'pretix.plugins.ticketoutputpdf': True
    }
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
    print(resp.data)
    assert TEST_EVENT_RES == dict(resp.data['results'][0])


@pytest.mark.django_db
def test_event_create(token_client, organizer, event):
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
                "type": "Conference"
            }
        },
        format='json'
    )

    assert resp.status_code == 201

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
    assert resp.content.decode() == '{"live":["You need to configure at least one quota to sell anything."]}'


@pytest.mark.django_db
def test_event_update(token_client, organizer, event, item):
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
    event = Event.objects.get(organizer=organizer.pk, slug=resp.data['slug'])
    assert event.currency == "DKK"

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
def test_event_update_live_no_payment_method(token_client, organizer, event, item):
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
            "plugins": {
                "pretix.plugins.banktransfer": False,
                "pretix.plugins.stripe": False,
                "pretix.plugins.paypal": False,
                "pretix.plugins.ticketoutputpdf": True,
                "pretix.plugins.sendmail": False,
                "pretix.plugins.statistics": False,
                "pretix.plugins.reports": False,
                "pretix.plugins.pretixdroid": True
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data.get('plugins') == {
        "pretix.plugins.banktransfer": False,
        "pretix.plugins.stripe": False,
        "pretix.plugins.paypal": False,
        "pretix.plugins.ticketoutputpdf": True,
        "pretix.plugins.sendmail": False,
        "pretix.plugins.statistics": False,
        "pretix.plugins.reports": False,
        "pretix.plugins.pretixdroid": True
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": {
                "pretix.plugins.banktransfer": True
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data.get('plugins') == {
        "pretix.plugins.banktransfer": True,
        "pretix.plugins.stripe": False,
        "pretix.plugins.paypal": False,
        "pretix.plugins.ticketoutputpdf": False,
        "pretix.plugins.sendmail": False,
        "pretix.plugins.statistics": False,
        "pretix.plugins.reports": False,
        "pretix.plugins.pretixdroid": False
    }

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": {
                "pretix.plugins.banktransfer": "Enabled",
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"plugins":["Illegal value \'Enabled\' for: \'pretix.plugins.banktransfer\'."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/'.format(organizer.slug, event.slug),
        {
            "plugins": {
                "pretix.plugins.test": True,
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
