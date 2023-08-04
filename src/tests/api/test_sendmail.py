#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import datetime

import pytest
from django_scopes import scopes_disabled

from pretix.plugins.sendmail.models import Rule


@pytest.fixture
def rule(event):
    return event.sendmail_rules.create(subject='test', template='foo',
                                       send_date=datetime.datetime(2021, 7, 8, tzinfo=datetime.timezone.utc))


TEST_RULE_RES = {
    'id': 1,
    'subject': {'en': 'test'},
    'template': {'en': 'foo'},
    'all_products': True,
    'limit_products': [],
    "restrict_to_status": ['p', 'n__valid_if_pending'],
    'send_date': '2021-07-08T00:00:00Z',
    'send_offset_days': None,
    'send_offset_time': None,
    'date_is_absolute': True,
    'offset_to_event_end': False,
    'offset_is_after': False,
    'send_to': 'orders',
    'enabled': True,
}


@pytest.mark.django_db
def test_sendmail_rule_list(token_client, organizer, event, rule):
    res = dict(TEST_RULE_RES)

    res['id'] = rule.pk

    resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/sendmail_rules/')
    assert resp.status_code == 200
    results = resp.data['results']
    assert res in results
    assert len(results) == 1

    produces_result = [f'id={rule.id}', 'all_products=true', 'date_is_absolute=true',
                       'offset_to_event_end=false', 'offset_is_after=false', 'send_to=orders', 'enabled=true',
                       f'id={rule.id}&enabled=true']

    no_produce_result = ['id=12345', 'all_products=false', 'date_is_absolute=false',
                         'offset_to_event_end=true', 'offset_is_after=true', 'send_to=both', 'send_to=attendees',
                         'enabled=false', f'id={rule.id}&enabled=false']

    for q in produces_result:
        resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/sendmail_rules/?{q}')
        assert [res] == resp.data['results']

    for q in no_produce_result:
        resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/sendmail_rules/?{q}')
        assert [] == resp.data['results']


@pytest.mark.django_db
def test_sendmail_rule_detail(token_client, organizer, event, rule):
    res = dict(TEST_RULE_RES)
    res['id'] = rule.pk

    resp = token_client.get(f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/sendmail_rules/{rule.pk}/')

    assert resp.status_code == 200
    assert res == resp.data


@scopes_disabled()
def create_rule(token_client, organizer, event, data, expected_failure=False, expected_failure_text=None):
    resp = token_client.post(
        f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/sendmail_rules/',
        data=data, format='json'
    )
    if expected_failure:
        assert resp.status_code == 400
        if expected_failure_text:
            assert expected_failure_text in resp.content.decode(resp.charset)
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
def test_sendmail_rule_offset_zero(token_client, organizer, event):
    create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z',
            'send_offset_days': '0',
            'send_offset_time': '08:40',
            'date_is_absolute': False,
        },
        expected_failure=False,
    )


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_create_minimal(token_client, organizer, event):
    r = create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z'
        }
    )
    assert r.send_date == datetime.datetime(2018, 3, 17, 13, 31, tzinfo=datetime.timezone.utc)


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
            "restrict_to_status": ['p', 'n__not_pending_approval_and_not_valid_if_pending', 'n__valid_if_pending'],
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
    assert r.restrict_to_status == ['p', 'n__not_pending_approval_and_not_valid_if_pending', 'n__valid_if_pending']
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
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
                'send_date': '2018-03-17T13:31Z',
                'offset_to_event_end': True,  # needs explicit date_is_absolute=False and specified offset
            },
            'date_is_absolute and offset_* are mutually exclusive'
        ),
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
                'send_date': '2018-03-17T13:31Z',
                'offset_is_after': True,
            },
            'date_is_absolute and offset_* are mutually exclusive'
        ),
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
                'send_date': '2018-03-17T13:31Z',
                'date_is_absolute': False,
            },
            'send_offset_days and send_offset_time are required'
        ),
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
                'send_date': '2018-03-17T13:31Z',
                'date_is_absolute': True,
                'offset_to_event_end': True,
                'send_offset_days': 2,
                'send_offset_time': '09:30',
            },
            'date_is_absolute and offset_* are mutually exclusive'
        ),
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
            },
            'send_date is required for date_is_absolute=True'
        ),
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
                'date_is_absolute': False,
                'offset_to_event_end': True,
            },
            'send_offset_days and send_offset_time are required'
        ),
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
                'send_date': '2018-03-17T13:31Z',
                'date_is_absolute': False,
                'offset_is_after': True,
                'send_offset_days': 2,
            },
            'send_offset_days and send_offset_time are required'
        ),
        (
            {
                'subject': {'en': 'foo'},
                'template': {'en': 'bar'},
                'date_is_absolute': False,
                'offset_is_after': True,
                'send_offset_time': '09:30',
            },
            'send_offset_days and send_offset_time are required'
        )
    ]

    for data, failure in invalid_examples:
        create_rule(token_client, organizer, event, data, expected_failure=True, expected_failure_text=failure)


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_legacy_field(token_client, organizer, event, rule):
    r = create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z',
            'include_pending': True
        }
    )
    assert r.restrict_to_status == ['p', 'n__not_pending_approval_and_not_valid_if_pending', 'n__valid_if_pending']

    r = create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z',
            'include_pending': False
        }
    )
    assert r.restrict_to_status == ['p', 'n__valid_if_pending']


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_restrict_recipients(token_client, organizer, event, rule):
    restrictions = ['p', 'e', 'c', 'n__not_pending_approval_and_not_valid_if_pending',
                    'n__pending_approval', 'n__valid_if_pending', 'n__pending_overdue']
    for r in restrictions:
        result = create_rule(
            token_client, organizer, event,
            data={
                'subject': {'en': 'meow'},
                'template': {'en': 'creative text here'},
                'send_date': '2018-03-17T13:31Z',
                "restrict_to_status": [r],
            },
            expected_failure=False
        )
        assert result.restrict_to_status == [r]

    create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z',
            "restrict_to_status": ["foo"],
        },
        expected_failure=True,
        expected_failure_text="restrict_to_status may only include valid states"
    )

    create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z',
            "restrict_to_status": [],
        },
        expected_failure=True,
        expected_failure_text="restrict_to_status needs at least one value"
    )

    create_rule(
        token_client, organizer, event,
        data={
            'subject': {'en': 'meow'},
            'template': {'en': 'creative text here'},
            'send_date': '2018-03-17T13:31Z',
        },
        expected_failure=False
    )


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_change(token_client, organizer, event, rule):
    token_client.patch(
        f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/sendmail_rules/{rule.pk}/',
        data={'enabled': False}, format='json'
    )

    rule.refresh_from_db()

    assert rule.enabled is False


@scopes_disabled()
@pytest.mark.django_db
def test_sendmail_rule_delete(token_client, organizer, event, rule):
    token_client.delete(
        f'/api/v1/organizers/{organizer.slug}/events/{event.slug}/sendmail_rules/{rule.pk}/'
    )

    assert Rule.objects.filter(pk=rule.pk).count() == 0
