#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import hashlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Event, Order, OrderPosition, Organizer, generate_secret,
)


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
    with scope(organizer=o):
        yield event


@pytest.fixture
def item(event):
    return event.items.create(
        name='Early-bird ticket',
        category=None, default_price=23,
        admission=True
    )


@pytest.fixture
def order(event, item):
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
        total=14, locale='en'
    )
    OrderPosition.objects.create(
        order=o,
        item=item,
        variation=None,
        price=Decimal("14"),
    )
    return o


@pytest.mark.django_db
def test_order_untagged_secret_compare(order):
    found = Order.objects.get_with_secret_check(order.code, order.secret, tag=None)
    assert found.code == order.code

    found = Order.objects.get_with_secret_check(order.code, order.secret.upper(), tag=None)
    assert found.code == order.code

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, order.secret + "X", tag=None)

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, order.secret, tag='foo')


@pytest.mark.django_db
def test_order_tagged_secret_compare(order):
    tagged_secret = order.tagged_secret('my_tag_123')

    found = Order.objects.get_with_secret_check(order.code, tagged_secret, tag='my_tag_123')
    assert found.code == order.code

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, 'X' + tagged_secret, tag='my_tag_123')

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, tagged_secret, tag=None)

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, tagged_secret, tag='some_other_tag')


@pytest.mark.django_db
def test_order_tagged_secret_allows_legacy_hashes(order):
    # TODO: remove this test when support for legacy hashes is removed, and enable the test below
    legacy_hash = hashlib.sha1(order.secret.encode('utf-8')).hexdigest()

    found = Order.objects.get_with_secret_check(order.code, legacy_hash, tag='my_tag_123')
    assert found.code == order.code


@pytest.mark.skip(reason="support for legacy hashes")  # TODO: enable this test when support for legacy hashes is removed
@pytest.mark.django_db
def test_order_tagged_secret_doesnt_allow_legacy_hashes(order):
    legacy_hash = hashlib.sha1(order.secret.encode('utf-8')).hexdigest()

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, legacy_hash, tag='my_tag_123')


@pytest.mark.django_db
def test_order_untagged_secret_doesnt_allow_legacy_hashes(order):
    legacy_hash = hashlib.sha1(order.secret.encode('utf-8')).hexdigest()

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, legacy_hash, tag=None)


@pytest.mark.django_db
def test_order_tagged_secret_independent(order):
    tagged_secret = order.tagged_secret('my_tag_123')

    found = Order.objects.get_with_secret_check(order.code, tagged_secret, tag='my_tag_123')
    assert found.code == order.code

    # a) still valid after order.secret change
    order.secret = generate_secret()
    order.save()

    found = Order.objects.get_with_secret_check(order.code, tagged_secret, tag='my_tag_123')
    assert found.code == order.code

    # b) invalidated after order.internal_secret change
    order.internal_secret = generate_secret()
    order.save()

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, tagged_secret, tag='my_tag_123')


@pytest.mark.django_db
def test_order_tagged_secret_uses_regular_secret_if_internal_secret_missing(order):
    order.internal_secret = None
    order.save()

    tagged_secret = order.tagged_secret('my_tag_123')

    found = Order.objects.get_with_secret_check(order.code, tagged_secret, tag='my_tag_123')
    assert found.code == order.code

    order.secret = generate_secret()
    order.save()

    with pytest.raises(Order.DoesNotExist):
        Order.objects.get_with_secret_check(order.code, tagged_secret, tag='my_tag_123')
