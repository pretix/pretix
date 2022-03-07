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
import copy
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer, Discount
from pretix.base.services.pricing import apply_discounts


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def item(event):
    return event.items.create(name='Ticket', default_price=Decimal('23.00'))


@pytest.fixture
def voucher(event):
    return event.vouchers.create()


@pytest.fixture
def subevent(event):
    event.has_subevents = True
    event.save()
    return event.subevents.create(name='Foobar', date_from=now())


mixed_min_count_matching_percent = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_MIXED,
        condition_min_count=3,
        benefit_discount_matching_percent=20
    ),
)
mixed_min_count_one_free = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_MIXED,
        condition_min_count=3,
        benefit_discount_matching_percent=100,
        benefit_only_apply_to_cheapest_n_matches=1,
    ),
)
mixed_min_value_matching_percent = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_MIXED,
        condition_min_value=500,
        benefit_discount_matching_percent=20
    ),
)
same_min_count_matching_percent = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_SAME,
        condition_min_count=3,
        benefit_discount_matching_percent=20
    ),
)
same_min_count_one_free = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_SAME,
        condition_min_count=3,
        benefit_discount_matching_percent=100,
        benefit_only_apply_to_cheapest_n_matches=1,
    ),
)
same_min_value_matching_percent = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_SAME,
        condition_min_value=500,
        benefit_discount_matching_percent=20
    ),
)
distinct_min_count_matching_percent = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_DISTINCT,
        condition_min_count=3,
        benefit_discount_matching_percent=20
    ),
)
distinct_min_count_one_free = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_DISTINCT,
        condition_min_count=3,
        benefit_discount_matching_percent=100,
        benefit_only_apply_to_cheapest_n_matches=1,
    ),
)
distinct_min_count_two_free = (
    Discount(
        subevent_mode=Discount.SUBEVENT_MODE_DISTINCT,
        condition_min_count=3,
        benefit_discount_matching_percent=100,
        benefit_only_apply_to_cheapest_n_matches=2,
    ),
)


testcases = [
    # mixed + min_count + matching_percent
    (
        mixed_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 2,
        (
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        mixed_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 3,
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
        )
    ),
    (
        mixed_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
        ),
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
        )
    ),

    # mixed + min_count + matching_percent + apply_to_cheapest
    (
        mixed_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 2,
        (
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        mixed_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 3,
        (
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        mixed_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 5,
        (
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        mixed_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 6,
        (
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        mixed_min_count_one_free,
        (
            (1, 1, Decimal('1.00'), False, False),
            (1, 1, Decimal('2.00'), False, False),
            (1, 1, Decimal('3.00'), False, False),
            (1, 1, Decimal('4.00'), False, False),
            (1, 1, Decimal('5.00'), False, False),
            (1, 1, Decimal('6.00'), False, False),
        ),
        (
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('3.00'),
            Decimal('4.00'),
            Decimal('5.00'),
            Decimal('6.00'),
        )
    ),

    # mixed + min_value + matching_percent
    (
        mixed_min_value_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 4,
        (
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        mixed_min_value_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 5,
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
        )
    ),
    (
        mixed_min_value_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
        ) * 10,
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
        )
    ),

    # same + min_count + matching_percent
    (
        same_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
        ),
        (
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        same_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
        ),
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        same_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
        ),
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('120.00'),
        )
    ),

    # same + min_count + matching_percent + apply_to_cheapest
    (
        same_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
        ),
        (
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        same_min_count_one_free,
        (
            (1, 1, Decimal('1.00'), False, False),
            (1, 1, Decimal('2.00'), False, False),
            (1, 1, Decimal('3.00'), False, False),
            (1, 2, Decimal('4.00'), False, False),
            (1, 2, Decimal('5.00'), False, False),
            (1, 2, Decimal('6.00'), False, False),
            (1, 2, Decimal('7.00'), False, False),
            (1, 3, Decimal('8.00'), False, False),
            (1, 3, Decimal('9.00'), False, False),
        ),
        (
            Decimal('0.00'),
            Decimal('2.00'),
            Decimal('3.00'),
            Decimal('0.00'),
            Decimal('5.00'),
            Decimal('6.00'),
            Decimal('7.00'),
            Decimal('8.00'),
            Decimal('9.00'),
        )
    ),

    # same + min_value + matching_percent
    (
        same_min_value_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
        ),
        (
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
        )
    ),

    # distinct + min_count + matching_percent
    (
        distinct_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
        ),
        (
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        distinct_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
        ),
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
        )
    ),
    (
        distinct_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
        ),
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        distinct_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 4, Decimal('120.00'), False, False),
        ),
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
        )
    ),
    (
        distinct_min_count_matching_percent,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 4, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
        ),
        (
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('96.00'),
            Decimal('120.00'),
        )
    ),

    # distinct + min_count + matching_percent + apply_to_cheapest
    (
        distinct_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
        ),
        (
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        distinct_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
        ),
        (
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
        )
    ),
    (
        distinct_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 4, Decimal('120.00'), False, False),
        ),
        (
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('0.00'),
        )
    ),
    (
        distinct_min_count_one_free,
        (
            (1, 1, Decimal('3.00'), False, False),
            (1, 2, Decimal('2.00'), False, False),
            (1, 3, Decimal('1.00'), False, False),
            (1, 1, Decimal('1.00'), False, False),
            (1, 2, Decimal('2.00'), False, False),
            (1, 4, Decimal('3.00'), False, False),
        ),
        (
            Decimal('3.00'),
            Decimal('2.00'),
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('2.00'),
            Decimal('3.00'),
        )
    ),
    (
        distinct_min_count_two_free,
        (
            (1, 1, Decimal('3.00'), False, False),
            (1, 2, Decimal('2.00'), False, False),
            (1, 3, Decimal('1.00'), False, False),
            (1, 1, Decimal('1.00'), False, False),
            (1, 2, Decimal('2.00'), False, False),
            (1, 4, Decimal('3.00'), False, False),
        ),
        (
            Decimal('3.00'),
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('3.00'),
        )
    ),
    (
        distinct_min_count_one_free,
        (
            (1, 1, Decimal('120.00'), False, False),
            (1, 2, Decimal('120.00'), False, False),
            (1, 3, Decimal('120.00'), False, False),
            (1, 4, Decimal('120.00'), False, False),
            (1, 5, Decimal('120.00'), False, False),
            (1, 6, Decimal('120.00'), False, False),
        ),
        (
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('0.00'),
            Decimal('120.00'),
            Decimal('120.00'),
            Decimal('0.00'),
        )
    ),
    (
        distinct_min_count_one_free,
        (
            (1, 1, Decimal('1.00'), False, False),
            (1, 2, Decimal('2.00'), False, False),
            (1, 3, Decimal('3.00'), False, False),
            (1, 4, Decimal('4.00'), False, False),
            (1, 5, Decimal('5.00'), False, False),
            (1, 6, Decimal('6.00'), False, False),
        ),
        (
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('3.00'),
            Decimal('4.00'),
            Decimal('5.00'),
            Decimal('6.00'),
        )
    ),
    (
        distinct_min_count_one_free,
        (
            (1, 1, Decimal('4.00'), False, False),
            (1, 2, Decimal('4.00'), False, False),
            (1, 3, Decimal('4.00'), False, False),
            (1, 1, Decimal('6.00'), False, False),
            (1, 2, Decimal('6.00'), False, False),
            (1, 3, Decimal('6.00'), False, False),
        ),
        (
            # This one is unexpected, since the customer could get a lower price
            # if they would split their order, but it's not really possible to solve
            # that without giving up other desired effects.
            Decimal('0.00'),
            Decimal('0.00'),
            Decimal('4.00'),
            Decimal('6.00'),
            Decimal('6.00'),
            Decimal('6.00'),
        )
    ),
]


@pytest.mark.parametrize("discounts,positions,expected", testcases)
@pytest.mark.django_db
@scopes_disabled()
def test_discount_evaluation(event, item, subevent, discounts, positions, expected):
    for d in discounts:
        d = copy.copy(d)
        d.event = event
        d.internal_name = 'Discount'
        d.full_clean()
        d.save()
    new_prices = apply_discounts(event, 'web', positions)
    print(new_prices)
    assert sorted(new_prices) == sorted(expected)

# todo: condition-less discount
# todo: apply_to_cheapest with != 100
# todo: evaluation order
# todo: sales_channels
# todo: available_from/until
# todo: condition_limit_products
# todo: condition_apply_to_addons
