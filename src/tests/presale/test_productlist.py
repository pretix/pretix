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

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Organizer
from pretix.presale.productlist import prepare_item_list_for_shop

# Tests for prepare_item_list_for_shop are really incomplete since historically, most features are
# tested on the test_event or test_widget layer. We'll slowly add new tests here to test closer to the
# source.


@pytest.fixture
def event():
    o = Organizer.objects.create(name='MRMCD', slug='mrmcd')
    e = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now(), live=True
    )
    with scope(organizer=o):
        yield e


@pytest.fixture
def quota(event):
    return event.quotas.create(name="Tickets", size=500)


@pytest.fixture
def item(event, quota):
    i = event.items.create(name="Ticket", default_price=Decimal("42.00"))
    quota.items.add(i)
    return i


@pytest.fixture
def variation(event, quota):
    i = event.items.create(name="Ticket with variants", default_price=Decimal("99.00"))
    v = i.variations.create(value="Default", default_price=Decimal("42.00"))
    quota.items.add(i)
    quota.variations.add(v)
    return v


@pytest.fixture
def discount(event):
    return event.discounts.create(
        internal_name="Early-Bird-Discount",
        all_sales_channels=True,
        available_from=now() - timedelta(days=2),
        available_until=now() + timedelta(days=2),
        condition_all_products=True,
        condition_min_count=1,
        benefit_discount_matching_percent=Decimal("10.00"),
    )


@pytest.fixture
def channel(event):
    return event.organizer.sales_channels.get(identifier="web")


@pytest.mark.django_db
def test_default_price(event, item, variation, channel):
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("42")
    assert items[1].available_variations[0].display_price.gross == Decimal("42")


def _test_no_discount(event, channel):
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("42")
    assert items[1].available_variations[0].display_price.gross == Decimal("42")


@pytest.mark.django_db
def test_discount_applied(event, item, variation, channel, discount):
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("37.80")
    assert items[0].original_price.gross == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("37.80")
    assert items[1].available_variations[0].original_price.gross == Decimal("42.00")


@pytest.mark.django_db
def test_discount_for_groups_ignored(event, item, variation, channel, discount):
    discount.condition_min_count = 2
    discount.save()
    _test_no_discount(event, channel)


@pytest.mark.django_db
def test_discount_original_price_kept(event, item, variation, channel, discount):
    item.original_price = Decimal("46.00")
    item.save()
    variation.original_price = Decimal("46.00")
    variation.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("37.80")
    assert items[0].original_price.gross == Decimal("46.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("37.80")
    assert items[1].available_variations[0].original_price.gross == Decimal("46.00")


@pytest.mark.django_db
def test_discount_out_of_timeframe(event, item, variation, channel, discount):
    discount.available_from = now() + timedelta(days=2)
    discount.save()
    _test_no_discount(event, channel)


@pytest.mark.django_db
def test_discount_wrong_channel(event, item, variation, channel, discount):
    discount.all_sales_channels = False
    discount.save()
    _test_no_discount(event, channel)


@pytest.mark.django_db
def test_discount_benefits_other_products_ignored(event, item, variation, channel, discount):
    discount.benefit_same_products = False
    discount.save()
    _test_no_discount(event, channel)


@pytest.mark.django_db
def test_discounts_for_addons(event, item, variation, channel, discount):
    discount.condition_apply_to_addons = False
    discount.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel, allow_addons=True)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("42.00")

    discount.condition_apply_to_addons = True
    discount.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel, allow_addons=True)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("37.80")
    assert items[1].available_variations[0].display_price.gross == Decimal("37.80")


@pytest.mark.django_db
def test_discounts_with_voucher(event, item, variation, channel, discount):
    voucher = event.vouchers.create(code="FOO", price_mode="subtract", value=Decimal("10.00"))
    voucher2 = event.vouchers.create(code="BAR")
    discount.condition_ignore_voucher_discounted = True
    discount.save()
    item.original_price = Decimal("46.00")
    item.save()
    variation.item.original_price = Decimal("46.00")
    variation.item.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel, voucher=voucher)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("32.00")
    assert items[0].original_price.gross == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("32.00")
    assert items[1].available_variations[0].original_price.gross == Decimal("42.00")
    items, _ = prepare_item_list_for_shop(event, channel=channel, voucher=voucher2)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("37.80")
    assert items[0].original_price.gross == Decimal("46.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("37.80")
    assert items[1].available_variations[0].original_price.gross == Decimal("46.00")

    discount.condition_ignore_voucher_discounted = False
    discount.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel, voucher=voucher)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("28.80")
    assert items[0].original_price.gross == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("28.80")
    assert items[1].available_variations[0].original_price.gross == Decimal("42.00")


@pytest.mark.django_db
def test_discounts_for_subevent_timeframe(event, quota, item, variation, channel, discount):
    event.has_subevents = True
    event.save()
    se = event.subevents.create(
        name="Foobar", date_from=datetime(2028, 12, 27, 10, 0, 0, tzinfo=UTC)
    )
    quota.subevent = se
    quota.save()

    discount.subevent_date_from = se.date_from + timedelta(days=1)
    discount.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel, subevent=se)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("42.00")

    discount.subevent_date_from = se.date_from - timedelta(days=1)
    discount.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel, subevent=se)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("37.80")
    assert items[1].available_variations[0].display_price.gross == Decimal("37.80")


@pytest.mark.django_db
def test_discounts_for_products(event, quota, item, variation, channel, discount):
    discount.condition_all_products = False
    discount.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("42.00")

    discount.condition_limit_products.add(item)
    discount.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("37.80")
    assert items[1].available_variations[0].display_price.gross == Decimal("37.80")


@pytest.mark.django_db
def test_discounts_for_products_tax_additive(event, quota, item, variation, channel, discount):
    tr = event.tax_rules.create(rate=Decimal("19.00"), price_includes_tax=False)
    item.tax_rule = tr
    item.save()
    variation.item.tax_rule = tr
    variation.item.save()
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("44.98")
    assert items[0].original_price.gross == Decimal("49.98")
    assert items[0].original_price.net == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("44.98")
    assert items[1].available_variations[0].original_price.gross == Decimal("49.98")
    assert items[1].available_variations[0].original_price.net == Decimal("42.00")


@pytest.mark.django_db
def test_discounts_for_products_tax_additive_bundle_included(event, quota, item, variation, channel, discount):
    tr = event.tax_rules.create(rate=Decimal("19.00"), price_includes_tax=False)
    b = event.items.create(name="Bundled product", default_price=Decimal("10.00"), tax_rule=tr, require_bundling=True)
    quota.items.add(b)
    item.tax_rule = tr
    item.save()
    variation.item.tax_rule = tr
    variation.item.save()
    item.bundles.create(bundled_item=b, count=2, designated_price=Decimal("5.00"))
    items, _ = prepare_item_list_for_shop(event, channel=channel)
    assert len(items) == 2
    assert items[0].display_price.gross == Decimal("45.98")
    assert items[0].original_price.gross == Decimal("49.98")
    assert items[0].original_price.net == Decimal("42.00")
    assert items[1].available_variations[0].display_price.gross == Decimal("45.98")
    assert items[1].available_variations[0].original_price.gross == Decimal("49.98")
    assert items[1].available_variations[0].original_price.net == Decimal("42.00")
