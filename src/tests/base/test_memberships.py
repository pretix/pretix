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
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django_scopes import scope
from freezegun import freeze_time

from pretix.base.i18n import language
from pretix.base.models import (
    CartPosition, Event, Item, Order, OrderPosition, Organizer,
)
from pretix.base.services.memberships import (
    membership_validity, validate_memberships_in_order,
)
from pretix.base.services.orders import (
    OrderError, _create_order, _perform_order,
)
from pretix.plugins.banktransfer.payment import BankTransfer

TZ = ZoneInfo('Europe/Berlin')


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    o.settings.customer_accounts = True
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=datetime(2021, 4, 27, 10, 0, 0, 0, tzinfo=TZ),
        date_to=datetime(2021, 4, 28, 10, 0, 0, 0, tzinfo=TZ),
        presale_end=datetime(2221, 4, 28, 10, 0, 0, 0, tzinfo=TZ),
        plugins='pretix.plugins.banktransfer'
    )
    event.settings.timezone = 'Europe/Berlin'
    with scope(organizer=o), language('en'):
        yield event


@pytest.fixture
def customer(event):
    return event.organizer.customers.create(email="john@example.org")


@pytest.fixture
def membership_type(event):
    return event.organizer.membership_types.create(name="Full pass")


@pytest.fixture
def membership(event, membership_type, customer):
    return customer.memberships.create(
        membership_type=membership_type,
        date_start=datetime(2021, 4, 1, 0, 0, 0, 0, tzinfo=TZ),
        date_end=datetime(2021, 4, 30, 23, 59, 59, 999999, tzinfo=TZ),
    )


@pytest.fixture
def granting_ticket(event, membership_type):
    return Item.objects.create(
        event=event, name='Full pass',
        default_price=Decimal('23.00'),
        admission=True,
        grant_membership_type=membership_type,
    )


@pytest.fixture
def requiring_ticket(event, membership_type):
    i = Item.objects.create(
        event=event, name='Day ticket',
        default_price=Decimal('23.00'),
        admission=True,
        require_membership=True,
    )
    i.require_membership_types.add(membership_type)
    return i


@pytest.fixture
def subevent(event):
    event.has_subevents = True
    return event.subevents.create(
        name='Foo',
        date_from=datetime(2021, 4, 29, 10, 0, 0, 0, tzinfo=TZ),
    )


@pytest.mark.django_db
def test_validity_membership_duration_like_event(event, granting_ticket, membership_type):
    granting_ticket.grant_membership_duration_like_event = True
    assert membership_validity(granting_ticket, None, event) == (
        datetime(2021, 4, 27, 10, 0, 0, 0, tzinfo=TZ),
        datetime(2021, 4, 28, 10, 0, 0, 0, tzinfo=TZ),
    )


@pytest.mark.django_db
def test_validity_membership_duration_like_subevent_without_end(event, granting_ticket, subevent, membership_type):
    granting_ticket.grant_membership_duration_like_event = True
    assert membership_validity(granting_ticket, subevent, event) == (
        datetime(2021, 4, 29, 10, 0, 0, 0, tzinfo=TZ),
        datetime(2021, 4, 29, 23, 59, 59, 999999, tzinfo=TZ),
    )


@pytest.mark.django_db
def test_validity_membership_duration_days(event, granting_ticket, membership_type):
    granting_ticket.grant_membership_duration_like_event = False
    granting_ticket.grant_membership_duration_days = 3
    with freeze_time("2021-04-10T11:00:00+02:00"):
        assert membership_validity(granting_ticket, subevent, event) == (
            datetime(2021, 4, 10, 0, 0, 0, 0, tzinfo=TZ),
            datetime(2021, 4, 12, 23, 59, 59, 999999, tzinfo=TZ),
        )


@pytest.mark.django_db
def test_validity_membership_duration_months(event, granting_ticket, membership_type):
    granting_ticket.grant_membership_duration_like_event = False
    granting_ticket.grant_membership_duration_months = 1
    with freeze_time("2021-02-01T11:00:00+01:00"):
        assert membership_validity(granting_ticket, subevent, event) == (
            datetime(2021, 2, 1, 0, 0, 0, 0, tzinfo=TZ),
            datetime(2021, 2, 28, 23, 59, 59, 999999, tzinfo=TZ),
        )
    with freeze_time("2021-02-28T11:00:00+01:00"):
        assert membership_validity(granting_ticket, subevent, event) == (
            datetime(2021, 2, 28, 0, 0, 0, 0, tzinfo=TZ),
            datetime(2021, 3, 27, 23, 59, 59, 999999, tzinfo=TZ),
        )


@pytest.mark.django_db
def test_validity_membership_duration_months_plus_days(event, granting_ticket, membership_type):
    granting_ticket.grant_membership_duration_like_event = False
    granting_ticket.grant_membership_duration_months = 1
    granting_ticket.grant_membership_duration_days = 2
    with freeze_time("2021-02-01T11:00:00+01:00"):
        assert membership_validity(granting_ticket, subevent, event) == (
            datetime(2021, 2, 1, 0, 0, 0, 0, tzinfo=TZ),
            datetime(2021, 3, 2, 23, 59, 59, 999999, tzinfo=TZ),
        )
    with freeze_time("2021-02-28T11:00:00+01:00"):
        assert membership_validity(granting_ticket, subevent, event) == (
            datetime(2021, 2, 28, 0, 0, 0, 0, tzinfo=TZ),
            datetime(2021, 3, 29, 23, 59, 59, 999999, tzinfo=TZ),
        )


@pytest.mark.django_db
def test_validate_membership_not_required(event, customer, membership, granting_ticket, membership_type):
    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=granting_ticket,
                    used_membership=membership,
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "does not require" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_required(event, customer, membership, requiring_ticket, membership_type):
    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "requires an active" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_ensure_locking(event, customer, membership, requiring_ticket, membership_type, django_assert_num_queries):
    with django_assert_num_queries(4) as captured:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership,
                )
            ],
            event,
            lock=True,
            ignored_order=None
        )
    if 'sqlite' not in settings.DATABASES['default']['ENGINE']:
        assert any('FOR UPDATE' in s['sql'] for s in captured)


@pytest.mark.django_db
def test_validate_membership_canceled(event, customer, membership, requiring_ticket, membership_type):
    with pytest.raises(ValidationError) as excinfo:
        membership.canceled = True
        membership.save()
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                )
            ],
            event,
            lock=False,
            ignored_order=None,
            testmode=False,
        )
    assert "canceled" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_test_mode(event, customer, membership, requiring_ticket, membership_type):
    with pytest.raises(ValidationError) as excinfo:
        membership.testmode = True
        membership.save()
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                )
            ],
            event,
            lock=False,
            ignored_order=None,
            testmode=False,
        )
    assert "test mode" in str(excinfo.value)
    with pytest.raises(ValidationError) as excinfo:
        membership.testmode = False
        membership.save()
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                )
            ],
            event,
            lock=False,
            ignored_order=None,
            testmode=True,
        )
    assert "test mode" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_wrong_customer(event, customer, membership, requiring_ticket, membership_type):
    customer2 = event.organizer.customers.create(email="doe@example.org")
    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer2,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "different customer" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_wrong_date(event, customer, membership, requiring_ticket, membership_type):
    membership.date_start -= timedelta(days=100)
    membership.date_end -= timedelta(days=100)
    membership.save()
    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "taking place at" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_wrong_type(event, customer, membership, requiring_ticket, membership_type):
    requiring_ticket.require_membership_types.clear()
    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "not allowed for the product" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_max_usages(event, customer, membership, requiring_ticket, membership_type):
    membership_type.max_usages = 1
    membership_type.allow_parallel_usage = True
    membership_type.save()
    o1 = Order.objects.create(
        status=Order.STATUS_PENDING,
        event=event,
        email='admin@localhost',
        datetime=now() - timedelta(days=3),
        expires=now() + timedelta(days=11),
        total=Decimal("23"),
    )
    OrderPosition.objects.create(
        order=o1,
        item=requiring_ticket,
        used_membership=membership,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Peter"}
    )

    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "more than 1 time" in str(excinfo.value)
    membership_type.max_usages = 2
    membership_type.save()
    validate_memberships_in_order(
        customer,
        [
            CartPosition(
                item=requiring_ticket,
                used_membership=membership
            )
        ],
        event,
        lock=False,
        ignored_order=None
    )

    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                ),
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership
                ),
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "more than 2 times" in str(excinfo.value)


@pytest.mark.django_db
def test_validate_membership_parallel(event, customer, membership, subevent, requiring_ticket, membership_type):
    se2 = event.subevents.create(
        name='Foo',
        date_from=datetime(2021, 4, 28, 10, 0, 0, 0, tzinfo=TZ),
    )

    membership_type.allow_parallel_usage = False
    membership_type.save()

    o1 = Order.objects.create(
        status=Order.STATUS_PENDING,
        event=event,
        email='admin@localhost',
        datetime=now() - timedelta(days=3),
        expires=now() + timedelta(days=11),
        total=Decimal("23"),
    )
    OrderPosition.objects.create(
        order=o1,
        item=requiring_ticket,
        used_membership=membership,
        variation=None,
        subevent=subevent,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Peter"}
    )

    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership,
                    subevent=subevent
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "different ticket at the same time" in str(excinfo.value)

    validate_memberships_in_order(
        customer,
        [
            CartPosition(
                item=requiring_ticket,
                used_membership=membership,
                subevent=se2
            )
        ],
        event,
        lock=False,
        ignored_order=None
    )

    with pytest.raises(ValidationError) as excinfo:
        validate_memberships_in_order(
            customer,
            [
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership,
                    subevent=se2
                ),
                CartPosition(
                    item=requiring_ticket,
                    used_membership=membership,
                    subevent=se2
                )
            ],
            event,
            lock=False,
            ignored_order=None
        )
    assert "different ticket at the same time" in str(excinfo.value)

    membership_type.allow_parallel_usage = True
    membership_type.save()
    validate_memberships_in_order(
        customer,
        [
            CartPosition(
                item=requiring_ticket,
                used_membership=membership,
                subevent=subevent
            )
        ],
        event,
        lock=False,
        ignored_order=None
    )


@pytest.mark.django_db
def test_use_membership(event, customer, membership, requiring_ticket):
    cp1 = CartPosition.objects.create(
        item=requiring_ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123",
        used_membership=membership
    )
    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=now(),
                          payment_requests=[{
                              "id": "test0",
                              "provider": "banktransfer",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "payment_amount": Decimal("23.00"),
                              "pprov": BankTransfer(event)
                          }],
                          locale='de', customer=customer)[0]
    assert order.positions.first().used_membership == membership


@pytest.mark.django_db
def test_use_membership_invalid(event, customer, membership, requiring_ticket):
    membership.date_start -= timedelta(days=100)
    membership.date_end -= timedelta(days=100)
    membership.save()
    cp1 = CartPosition.objects.create(
        item=requiring_ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123",
        used_membership=membership
    )
    with pytest.raises(OrderError) as excinfo:
        _perform_order(event, email='dummy@example.org', position_ids=[cp1.pk],
                       payment_requests=[{
                           "id": "test0",
                           "provider": "banktransfer",
                           "max_value": None,
                           "min_value": None,
                           "multi_use_supported": False,
                           "info_data": {},
                       }],
                       address=None,
                       locale='de', customer=customer.pk)[0]
    assert 'membership' in str(excinfo.value)


@pytest.mark.django_db
def test_grant_when_paid_and_changed(event, customer, granting_ticket):
    cp1 = CartPosition.objects.create(
        item=granting_ticket, price=23, expires=now() + timedelta(days=1), event=event, cart_id="123",
    )
    q = event.quotas.create(size=None, name="foo")
    q.items.add(granting_ticket)
    order = _create_order(event, email='dummy@example.org', positions=[cp1],
                          now_dt=now(),
                          payment_requests=[{
                              "id": "test0",
                              "provider": "banktransfer",
                              "max_value": None,
                              "min_value": None,
                              "multi_use_supported": False,
                              "info_data": {},
                              "pprov": BankTransfer(event),
                              "payment_amount": Decimal("23.00"),
                          }],
                          locale='de', customer=customer)[0]
    assert not customer.memberships.exists()

    order.payments.first().confirm()

    m = customer.memberships.get()
    assert m.granted_in == order.positions.first()
    assert m.membership_type == granting_ticket.grant_membership_type
    assert m.date_start == datetime(2021, 4, 27, 10, 0, 0, 0, tzinfo=TZ)
    assert m.date_end == datetime(2021, 4, 28, 10, 0, 0, 0, tzinfo=TZ)
