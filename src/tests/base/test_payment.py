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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Christopher Dambamuromo
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils.timezone import now
from django_scopes import scope
from tests.testdummy.payment import DummyPaymentProvider

from pretix.base.models import (
    CartPosition, Event, Item, Order, OrderPosition, Organizer,
)
from pretix.base.reldate import RelativeDate, RelativeDateWrapper


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    with scope(organizer=o):
        yield event


@pytest.mark.django_db
def test_payment_fee_forward(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.30'))
    prov.settings.set('_fee_percent', Decimal('5.00'))
    prov.settings.set('_fee_reverse_calc', False)
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('5.30')


@pytest.mark.django_db
def test_payment_fee_reverse_percent(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.00'))
    prov.settings.set('_fee_percent', Decimal('5.00'))
    prov.settings.set('_fee_reverse_calc', True)
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('5.26')


@pytest.mark.django_db
def test_payment_fee_reverse_percent_and_abs(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.30'))
    prov.settings.set('_fee_percent', Decimal('2.90'))
    prov.settings.set('_fee_reverse_calc', True)
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('3.30')


@pytest.mark.django_db
def test_payment_fee_reverse_percent_and_abs_default(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_fee_abs', Decimal('0.30'))
    prov.settings.set('_fee_percent', Decimal('2.90'))
    assert prov.calculate_fee(Decimal('100.00')) == Decimal('3.30')


@pytest.mark.django_db
def test_availability_date_available(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', datetime.date.today() + datetime.timedelta(days=1))
    result = prov._is_still_available()
    assert result


@pytest.mark.django_db
def test_availability_date_not_available(event):
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', datetime.date.today() - datetime.timedelta(days=1))
    result = prov._is_still_available()
    assert not result


@pytest.mark.django_db
def test_availability_date_relative(event):
    event.settings.set('timezone', 'US/Pacific')
    tz = ZoneInfo('US/Pacific')
    event.date_from = datetime.datetime(2016, 12, 3, 12, 0, 0, tzinfo=tz)
    event.save()
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=2, time=None, base_date_name='date_from', minutes_before=None)
    ))

    utc = datetime.timezone.utc
    assert prov._is_still_available(datetime.datetime(2016, 11, 30, 23, 0, 0, tzinfo=tz).astimezone(utc))
    assert prov._is_still_available(datetime.datetime(2016, 12, 1, 23, 59, 0, tzinfo=tz).astimezone(utc))
    assert not prov._is_still_available(datetime.datetime(2016, 12, 2, 0, 0, 1, tzinfo=tz).astimezone(utc))


@pytest.mark.django_db
def test_availability_date_timezones(event):
    event.settings.set('timezone', 'US/Pacific')
    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', '2016-12-01')

    tz = ZoneInfo('US/Pacific')
    utc = ZoneInfo('UTC')
    assert prov._is_still_available(datetime.datetime(2016, 11, 30, 23, 0, 0, tzinfo=tz).astimezone(utc))
    assert prov._is_still_available(datetime.datetime(2016, 12, 1, 23, 59, 0, tzinfo=tz).astimezone(utc))
    assert not prov._is_still_available(datetime.datetime(2016, 12, 2, 0, 0, 1, tzinfo=tz).astimezone(utc))


@pytest.mark.django_db
def test_availability_date_cart_relative_subevents(event):
    event.date_from = now() + datetime.timedelta(days=5)
    event.has_subevents = True
    event.save()
    tr7 = event.tax_rules.create(rate=Decimal('7.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr7,
                                 default_price=Decimal('23.00'), admission=True)

    se1 = event.subevents.create(name="SE1", date_from=now() + datetime.timedelta(days=10))
    se2 = event.subevents.create(name="SE2", date_from=now() + datetime.timedelta(days=3))

    CartPosition.objects.create(
        item=ticket, price=23, expires=now() + datetime.timedelta(days=1), subevent=se1, event=event, cart_id="123"
    )
    CartPosition.objects.create(
        item=ticket, price=23, expires=now() + datetime.timedelta(days=1), subevent=se2, event=event, cart_id="123"
    )

    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=3, time=None, base_date_name='date_from', minutes_before=None)
    ))
    assert prov._is_still_available(cart_id="123")

    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=4, time=None, base_date_name='date_from', minutes_before=None)
    ))
    assert not prov._is_still_available(cart_id="123")


@pytest.mark.django_db
def test_availability_date_order_relative_subevents(event):
    event.date_from = now() + datetime.timedelta(days=5)
    event.has_subevents = True
    event.save()
    tr7 = event.tax_rules.create(rate=Decimal('7.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr7,
                                 default_price=Decimal('23.00'), admission=True)

    se1 = event.subevents.create(name="SE1", date_from=now() + datetime.timedelta(days=10))
    se2 = event.subevents.create(name="SE2", date_from=now() + datetime.timedelta(days=3))

    order = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + datetime.timedelta(days=10),
        total=Decimal('46.00'),
    )
    OrderPosition.objects.create(
        order=order, item=ticket, variation=None, subevent=se1,
        price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    OrderPosition.objects.create(
        order=order, item=ticket, variation=None, subevent=se2,
        price=Decimal("23.00"), attendee_name_parts={'full_name': "Dieter"}, positionid=2
    )

    prov = DummyPaymentProvider(event)
    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=3, time=None, base_date_name='date_from', minutes_before=None)
    ))
    assert prov._is_still_available(order=order)

    prov.settings.set('_availability_date', RelativeDateWrapper(
        RelativeDate(days_before=4, time=None, base_date_name='date_from', minutes_before=None)
    ))
    assert not prov._is_still_available(order=order)
