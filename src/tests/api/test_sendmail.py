import datetime

import pytest
from django.utils.timezone import utc
from django_scopes import scopes_disabled

from pretix.plugins.sendmail.models import Rule


@pytest.fixture
def rule(event):
    return event.sendmail_rules.create(subject='test', template='foo',
                                       send_date=datetime.datetime(2021, 7, 8, tzinfo=utc))


TEST_RULE_RES = {
    'id': 1,
    'subject': {'en': 'test'},
    'template': {'en': 'foo'},
    'all_products': True,
    'limit_products': [],
    'include_pending': False,
    'send_date': '2021-07-08T00:00:00Z',
    'send_offset_days': None,
    'send_offset_time': None,
    'date_is_absolute': True,
    'offset_to_event_end': False,
    'offset_is_after': False,
    'send_to': 'orders',
    'enabled': True,
    'event': 1,
}


@pytest.mark.django_db
def test_sendmail_rule_list(token_client, organizer, event, rule):
    res = dict(TEST_RULE_RES)

    res['id'] = rule.pk

    resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/mailrules/')
    assert resp.status_code == 200
    results = resp.data['results']
    assert res in results
    assert len(results) == 1

    produces_result = [f'id={rule.id}', 'all_products=true', 'include_pending=false', 'date_is_absolute=true',
                       'offset_to_event_end=false', 'offset_is_after=false', 'send_to=orders', 'enabled=true',
                       f'id={rule.id}&enabled=true']

    no_produce_result = ['id=12345', 'all_products=false', 'include_pending=true', 'date_is_absolute=false',
                         'offset_to_event_end=true', 'offset_is_after=true', 'send_to=both', 'send_to=attendees',
                         'enabled=false', f'id={rule.id}&enabled=false']

    for q in produces_result:
        resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/mailrules/?{q}')
        assert [res] == resp.data['results']

    for q in no_produce_result:
        resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/mailrules/?{q}')
        assert [] == resp.data['results']


@pytest.mark.django_db
def test_sendmail_rule_detail(token_client, organizer, event, rule):
    res = dict(TEST_RULE_RES)
    res['id'] = rule.pk

    resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/mailrules/{rule.pk}/')

    assert resp.status_code == 200
    assert res == resp.data


@scopes_disabled()
def create_rule(token_client, organizer, event, data, expected_failure=False):
    resp = token_client.post(
        f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/mailrules/',
        data=data, format='json'
    )
    if expected_failure:
        assert resp.status_code == 400
    else:
        assert resp.status_code == 201
        with scopes_disabled():
            return Rule.objects.get(pk=resp.data['id'])


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_create_min_fail(token_client, organizer, event):
    create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'not foobar'}
        },
        expected_failure=True
    )


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_create_minimal(token_client, organizer, event):
    r = create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z',
        }
    )
    assert r.send_date == datetime.datetime(2018, 3, 17, 13, 31, tzinfo=utc)


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_create_full(token_client, organizer, event, item):
    r = create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'mew'},
            'template': {'en': 'foobar'},
            'all_products': False,
            'limit_products': [event.items.first().pk],
            'include_pending': True,
            'send_offset_days': 3,
            'send_offset_time': '09:30',
            'date_is_absolute': False,
            'offset_to_event_end': True,
            'offset_is_after': True,
            'send_to': 'both',
            'enabled': False,
        }
    )

    assert r.all_products is False
    assert [i.pk for i in r.limit_products.all()] == [event.items.first().pk]
    assert r.include_pending is True
    assert r.send_offset_days == 3
    assert r.send_offset_time == datetime.time(9, 30)
    assert r.date_is_absolute is False
    assert r.offset_to_event_end is True
    assert r.offset_is_after is True
    assert r.send_to == 'both'
    assert r.enabled is False


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_create_invalid(token_client, organizer, event):
    invalid_examples = [
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
            'send_date': '2018-03-17T13:31Z',
            'offset_to_event_end': True,  # needs explicit date_is_absolute=False and specified offset
        },
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
            'send_date': '2018-03-17T13:31Z',
            'offset_is_after': True,
        },
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
            'send_date': '2018-03-17T13:31Z',
            'date_is_absolute': False,
        },
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
            'send_date': '2018-03-17T13:31Z',
            'date_is_absolute': True,
            'offset_to_event_end': True,
            'send_offset_days': 2,
            'send_offset_time': '09:30',
        },
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
        },
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
            'date_is_absolute': False,
            'offset_to_event_end': True,
        },
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
            'send_date': '2018-03-17T13:31Z',
            'date_is_absolute': False,
            'offset_is_after': True,
            'send_offset_days': 2,
        },
        {
            'subject': {'en': 'foo'},
            'template': {'en': 'bar'},
            'date_is_absolute': False,
            'offset_is_after': True,
            'send_offset_time': '09:30',
        }
    ]

    for data in invalid_examples:
        create_rule(token_client, organizer, event, data, expected_failure=True)


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_change(token_client, organizer, event, rule):
    token_client.patch(
        f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/mailrules/{rule.pk}/',
        data={'enabled': False}, format='json'
    )

    rule.refresh_from_db()

    assert rule.enabled is False


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_delete(token_client, organizer, event, rule):
    token_client.delete(
        f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/mailrules/{rule.pk}/'
    )

    assert Rule.objects.filter(pk=rule.pk).count() == 0
