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
# This file contains Apache-licensed contributions copyrighted by: Patrick Arminio, Ture Gjørup, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django_countries.fields import Country
from django_scopes import scopes_disabled
from tests.const import SAMPLE_PNG

from pretix.base.models import (
    CartPosition, InvoiceAddress, Item, ItemAddOn, ItemBundle, ItemCategory,
    ItemVariation, Order, OrderPosition, Question, QuestionOption, Quota,
)
from pretix.base.models.orders import OrderFee


@pytest.fixture
def category(event):
    return event.categories.create(name="Tickets")


@pytest.fixture
def category2(event2):
    return event2.categories.create(name="Tickets2")


@pytest.fixture
def category3(event, item):
    cat = event.categories.create(name="Tickets")
    item.category = cat
    item.save()
    return cat


@pytest.fixture
def order(event, item, taxrule):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
            datetime=datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
            expires=datetime(2017, 12, 10, 10, 0, 0, tzinfo=timezone.utc),
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
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


@pytest.fixture
def cart_position(event, item, variations):
    testtime = datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        c = CartPosition.objects.create(
            event=event,
            item=item,
            datetime=testtime,
            expires=testtime + timedelta(days=1),
            variation=variations[0],
            price=Decimal("23"),
            cart_id="z3fsn8jyufm5kpk768q69gkbyr5f4h6w"
        )
        return c


TEST_CATEGORY_RES = {
    "name": {"en": "Tickets"},
    "description": {"en": ""},
    "internal_name": None,
    "position": 0,
    "is_addon": False,
    "cross_selling_mode": None,
    "cross_selling_condition": None,
    "cross_selling_match_products": [],
}


@pytest.mark.django_db
def test_category_list(token_client, organizer, event, team, category):
    res = dict(TEST_CATEGORY_RES)
    res["id"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/?is_addon=false'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/?is_addon=true'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']
    category.is_addon = True
    category.save()
    res["is_addon"] = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/?is_addon=true'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    category.log_action('foo')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    lmd = resp['Last-Modified']
    assert lmd
    time.sleep(1)
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/'.format(
        organizer.slug, event.slug), HTTP_IF_MODIFIED_SINCE=lmd)
    assert resp.status_code == 304
    time.sleep(1)
    category.log_action('foo')
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/'.format(
        organizer.slug, event.slug), HTTP_IF_MODIFIED_SINCE=lmd)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_category_detail(token_client, organizer, event, team, category):
    res = dict(TEST_CATEGORY_RES)
    res["id"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event.slug,
                                                                                    category.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_category_create(token_client, organizer, event, team):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/categories/'.format(organizer.slug, event.slug),
        {
            "name": {"en": "Tickets"},
            "description": {"en": ""},
            "position": 0,
            "is_addon": False
        },
        format='json'
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_category_update(token_client, organizer, event, team, category):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event.slug, category.pk),
        {
            "name": {"en": "Test"},
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert ItemCategory.objects.get(pk=category.pk).name == {"en": "Test"}


@pytest.mark.django_db
def test_category_update_cross_selling_options(token_client, organizer, event, team, category):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event.slug, category.pk),
        {
            "cross_selling_mode": "both",
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert ItemCategory.objects.get(pk=category.pk).cross_selling_mode == 'both'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event.slug, category.pk),
        {
            "cross_selling_mode": "something",
        },
        format='json'
    )
    assert resp.status_code == 400
    with scopes_disabled():
        assert ItemCategory.objects.get(pk=category.pk).cross_selling_mode == 'both'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event.slug, category.pk),
        {
            "is_addon": True,
        },
        format='json'
    )
    assert resp.status_code == 400
    assert 'mutually exclusive' in str(resp.data)
    with scopes_disabled():
        assert ItemCategory.objects.get(pk=category.pk).cross_selling_mode == 'both'
        assert ItemCategory.objects.get(pk=category.pk).is_addon is False


@pytest.mark.django_db
def test_category_update_wrong_event(token_client, organizer, event2, category):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event2.slug, category.pk),
        {
            "name": {"en": "Test"},
        },
        format='json'
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_category_delete(token_client, organizer, event, category3, item):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/categories/{}/'.format(organizer.slug, event.slug, category3.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.categories.filter(pk=category3.id).exists()
        assert Item.objects.get(pk=item.pk).category is None


@pytest.fixture
def item(event):
    item = event.items.create(name="Budget Ticket", default_price=23)
    item.meta_values.create(property=event.item_meta_properties.first(), value="Tuesday")
    return item


@pytest.fixture
def item2(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item3(event):
    return event.items.create(name="Budget Ticket", default_price=23)


TEST_ITEM_RES = {
    "name": {"en": "Budget Ticket"},
    "internal_name": None,
    "default_price": "23.00",
    "sales_channels": ["bar", "baz", "web"],
    "all_sales_channels": True,
    "limit_sales_channels": [],
    "category": None,
    "active": True,
    "description": None,
    "free_price": False,
    "tax_rate": "0.00",
    "tax_rule": None,
    "admission": False,
    "personalized": False,
    "issue_giftcard": False,
    "position": 0,
    "generate_tickets": None,
    "allow_waitinglist": True,
    "picture": None,
    "available_from": None,
    "available_until": None,
    "available_from_mode": "hide",
    "available_until_mode": "hide",
    "require_bundling": False,
    "require_voucher": False,
    "hide_without_voucher": False,
    "allow_cancel": True,
    "min_per_order": None,
    "max_per_order": None,
    "hidden_if_available": None,
    "hidden_if_item_available": None,
    "hidden_if_item_available_mode": "hide",
    "checkin_attention": False,
    "checkin_text": None,
    "has_variations": False,
    "require_approval": False,
    "variations": [],
    "addons": [],
    "bundles": [],
    "show_quota_left": None,
    "original_price": None,
    "free_price_suggestion": None,
    "meta_data": {
        "day": "Tuesday"
    },
    "require_membership": False,
    "require_membership_hidden": False,
    "require_membership_types": [],
    "grant_membership_type": None,
    "grant_membership_duration_like_event": True,
    "grant_membership_duration_days": 0,
    "grant_membership_duration_months": 0,
    "media_policy": None,
    "media_type": None,
    "validity_mode": None,
    "validity_fixed_from": None,
    "validity_fixed_until": None,
    "validity_dynamic_duration_minutes": None,
    "validity_dynamic_duration_hours": None,
    "validity_dynamic_duration_days": None,
    "validity_dynamic_duration_months": None,
    "validity_dynamic_start_choice": False,
    "validity_dynamic_start_choice_day_limit": None,
}


@pytest.mark.django_db
def test_item_list(token_client, organizer, event, team, item):
    cat = event.categories.create(name="foo")
    res = dict(TEST_ITEM_RES)
    res["id"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?active=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?active=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?category={}'.format(organizer.slug, event.slug,
                                                                                        cat.pk))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    item.admission = True
    item.save()
    res['admission'] = True

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?admission=false'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?tax_rate=0'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?tax_rate=19'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?free_price=true'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?search=Budget'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/?search=Free'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_item_detail(token_client, organizer, event, team, item):
    res = dict(TEST_ITEM_RES)
    res["id"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_item_detail_variations(token_client, organizer, event, team, item):
    with scopes_disabled():
        var = item.variations.create(value="Children")
        res = dict(TEST_ITEM_RES)
        res["id"] = item.pk
        res["variations"] = [{
            "id": var.pk,
            "value": {"en": "Children"},
            "default_price": None,
            "free_price_suggestion": None,
            "price": "23.00",
            "active": True,
            "description": None,
            "position": 0,
            "checkin_attention": False,
            "checkin_text": None,
            "require_approval": False,
            "require_membership": False,
            "require_membership_hidden": False,
            "require_membership_types": [],
            "sales_channels": sorted(organizer.sales_channels.values_list("identifier", flat=True)),
            "all_sales_channels": True,
            "limit_sales_channels": [],
            "available_from": None,
            "available_until": None,
            "available_from_mode": "hide",
            "available_until_mode": "hide",
            "hide_without_voucher": False,
            "original_price": None,
            "meta_data": {}
        }]
    res["has_variations"] = True
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res['variations'] == resp.data['variations']


@pytest.mark.django_db
def test_item_detail_addons(token_client, organizer, event, team, item, category):
    item.addons.create(addon_category=category)
    res = dict(TEST_ITEM_RES)

    res["id"] = item.pk
    res["addons"] = [{
        "addon_category": category.pk,
        "min_count": 0,
        "max_count": 1,
        "position": 0,
        "multi_allowed": False,
        "price_included": False,
    }]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_item_detail_bundles(token_client, organizer, event, team, item, category):
    with scopes_disabled():
        i = event.items.create(name="Included thing", default_price=2)
        item.bundles.create(bundled_item=i, count=1, designated_price=2)
    res = dict(TEST_ITEM_RES)

    res["id"] = item.pk
    res["bundles"] = [{
        "bundled_item": i.pk,
        "bundled_variation": None,
        "count": 1,
        "designated_price": '2.00',
    }]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug,
                                                                               item.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_item_create(token_client, organizer, event, item, category, taxrule, membership_type):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "sales_channels": ["web", "bar"],
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,

            "has_variations": True,
            "require_membership_types": [membership_type.pk],
            "meta_data": {
                "day": "Wednesday"
            }
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        i = Item.objects.get(pk=resp.data['id'])
        assert not i.all_sales_channels
        assert sorted(i.limit_sales_channels.values_list("identifier", flat=True)) == ["bar", "web"]
        assert i.meta_data == {'day': 'Wednesday'}
        assert i.require_membership_types.count() == 1
        assert i.personalized is True  # auto-set for backwards-compatibility
        assert i.admission is True


@pytest.mark.django_db
def test_item_create_price_required(token_client, organizer, event, item, category, taxrule):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {"default_price": ["This field is required."]}
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": None,
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {"default_price": ["This field may not be null."]}


@pytest.mark.django_db
def test_item_create_with_variation(token_client, organizer, event, item, category, taxrule):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "variations": [
                {
                    "value": {
                        "de": "Kommentar",
                        "en": "Comment"
                    },
                    "active": True,
                    "require_approval": True,
                    "checkin_attention": False,
                    "checkin_text": None,
                    "require_membership": False,
                    "require_membership_hidden": False,
                    "require_membership_types": [],
                    "description": None,
                    "position": 0,
                    "default_price": None,
                    "price": "23.00",
                    "meta_data": {
                        "day": "Wednesday",
                    },
                },
                {
                    "value": {
                        "de": "web",
                        "en": "web"
                    },
                    "active": True,
                    "require_approval": True,
                    "checkin_attention": False,
                    "checkin_text": None,
                    "require_membership": False,
                    "require_membership_hidden": False,
                    "require_membership_types": [],
                    "description": None,
                    "position": 0,
                    "default_price": None,
                    "sales_channels": ["web"],
                    "price": "23.00",
                    "meta_data": {
                        "day": "Wednesday",
                    },
                },
            ]
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        new_item = Item.objects.get(pk=resp.data['id'])
        assert new_item.variations.first().value.localize('de') == "Kommentar"
        assert new_item.variations.first().value.localize('en') == "Comment"
        assert new_item.variations.first().require_approval is True
        assert new_item.variations.first().all_sales_channels is True
        assert not new_item.variations.first().limit_sales_channels.exists()
        assert new_item.variations.first().meta_data == {"day": "Wednesday"}
        assert new_item.variations.last().all_sales_channels is False
        assert new_item.variations.last().limit_sales_channels.exists()


@pytest.mark.django_db
def test_item_create_giftcard_validation(token_client, organizer, event, item, category, category2, taxrule, taxrule0):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule0.pk,
            "admission": True,
            "issue_giftcard": True,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "addons": []
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Gift card products should not be admission products at the same time."]}'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": False,
            "issue_giftcard": True,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "addons": []
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Gift card products should not be associated with non-zero ' \
                                    'tax rates since sales tax will be applied when the gift card is redeemed."]}'


@pytest.mark.django_db
def test_item_create_with_addon(token_client, organizer, event, item, category, category2, taxrule):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "addons": [
                {
                    "addon_category": category.pk,
                    "min_count": 0,
                    "max_count": 10,
                    "position": 0,
                    "multi_allowed": False,
                    "price_included": True
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        item = Item.objects.get(pk=resp.data['id'])
        assert item.addons.first().addon_category == category
        assert item.addons.first().max_count == 10
        assert 2 == Item.objects.all().count()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "addons": [
                {
                    "addon_category": category2.pk,
                    "min_count": 0,
                    "max_count": 10,
                    "position": 0,
                    "multi_allowed": False,
                    "price_included": True
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"addons":["The add-on\'s category must belong to the same event as the item."]}'
    with scopes_disabled():
        assert 2 == Item.objects.all().count()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "addons": [
                {
                    "addon_category": category.pk,
                    "min_count": 110,
                    "max_count": 10,
                    "position": 0,
                    "multi_allowed": False,
                    "price_included": True
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"addons":["The maximum count needs to be greater than the minimum count."]}'
    with scopes_disabled():
        assert 2 == Item.objects.all().count()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": True,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "addons": [
                {
                    "addon_category": category.pk,
                    "min_count": -1,
                    "max_count": 10,
                    "position": 0,
                    "multi_allowed": False,
                    "price_included": True
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() in [
        '{"addons":["The minimum count needs to be equal to or greater than zero."]}',
        '{"addons":[{"min_count":["Ensure this value is greater than or equal to 0."]}]}',
    ]
    with scopes_disabled():
        assert 2 == Item.objects.all().count()


@pytest.mark.django_db
def test_item_create_with_bundle(token_client, organizer, event, item, category, item2, taxrule):
    with scopes_disabled():
        i = event.items.create(name="Included thing", default_price=2)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "bundles": [
                {
                    "bundled_item": i.pk,
                    "bundled_variation": None,
                    "count": 2,
                    "designated_price": "3.00",
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        item = Item.objects.get(pk=resp.data['id'])
        b = item.bundles.first()
    assert b.bundled_item == i
    assert b.bundled_variation is None
    assert b.count == 2
    assert b.designated_price == 3

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "bundles": [
                {
                    "bundled_item": item2.pk,
                    "bundled_variation": None,
                    "count": 2,
                    "designated_price": "3.00",
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"bundles":["The bundled item must belong to the same event as the item."]}'

    with scopes_disabled():
        v = item2.variations.create(value="foo")
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "category": category.pk,
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "tax_rate": "19.00",
            "tax_rule": taxrule.pk,
            "admission": True,
            "position": 0,
            "picture": None,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "bundles": [
                {
                    "bundled_item": item.pk,
                    "bundled_variation": v.pk,
                    "count": 2,
                    "designated_price": "3.00",
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"bundles":["The chosen variation does not belong to this item."]}'


@pytest.mark.django_db(transaction=True)
def test_item_update(token_client, organizer, event, item, category, item2, category2, taxrule2):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "min_per_order": 1,
            "max_per_order": 2
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert Item.objects.get(pk=item.pk).max_per_order == 2

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "min_per_order": 10,
            "max_per_order": 2
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The maximum number per order can not be lower than the ' \
                                    'minimum number per order."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "available_from": "2017-12-30T12:00",
            "available_until": "2017-12-29T12:00"
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The item\'s availability cannot end before it starts."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "category": category2.pk
        },
        format='json'

    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"category":["The item\'s category must belong to the same event as the item."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "tax_rule": taxrule2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"tax_rule":["The item\'s tax rule must belong to the same event as the item."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "addons": [
                {
                    "addon_category": category.pk,
                    "min_count": 0,
                    "max_count": 10,
                    "position": 0,
                    "multi_allowed": False,
                    "price_included": True
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Updating add-ons, bundles, or variations via PATCH/PUT is not supported. Please use ' \
                                    'the dedicated nested endpoint."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "bundles": [
                {
                    "bundled_item": item2.pk,
                    "bundled_variation": None,
                    "count": 2,
                    "designated_price": "3.00",
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Updating add-ons, bundles, or variations via PATCH/PUT is not supported. Please use ' \
                                    'the dedicated nested endpoint."]}'

    item.personalized = True
    item.admission = True
    item.save()

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "meta_data": {
                "day": "Friday"
            }
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert Item.objects.get(pk=item.pk).meta_data == {'day': 'Friday'}

    item.refresh_from_db()
    assert item.admission
    assert item.personalized

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "meta_data": {
                "foo": "bar"
            }
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"meta_data":["Item meta data property \'foo\' does not exist."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "admission": False,
            "personalized": True,
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Only admission products can currently be personalized."]}'

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "admission": False
        },
        format='json'
    )
    assert resp.status_code == 200
    item.refresh_from_db()
    assert not item.admission
    assert not item.personalized  # also set for backwards compatibility


@pytest.mark.django_db
def test_item_file_upload(token_client, organizer, event, item):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'image/png',
            'file': ContentFile(SAMPLE_PNG)
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 201
    file_id_png = r.data['id']

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "picture": file_id_png,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert resp.data['picture'].startswith('http')
    assert '/pub/' in resp.data['picture']
    assert os.path.exists(os.path.join(settings.MEDIA_ROOT, resp.data['picture'].split('/media/')[1]))

    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'image/png',
            'file': ContentFile(SAMPLE_PNG)
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 201
    file_id_png = r.data['id']

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/'.format(organizer.slug, event.slug),
        {
            "name": {
                "en": "Ticket"
            },
            "active": True,
            "sales_channels": ["web"],
            "picture": file_id_png,
            "description": None,
            "default_price": "23.00",
            "free_price": False,
            "admission": True,
            "issue_giftcard": False,
            "position": 0,
            "available_from": None,
            "available_until": None,
            "require_voucher": False,
            "hide_without_voucher": False,
            "allow_cancel": True,
            "min_per_order": None,
            "max_per_order": None,
            "checkin_attention": False,
            "checkin_text": None,
            "has_variations": True,
            "meta_data": {
                "day": "Wednesday"
            }
        },
        format='json'
    )
    assert resp.status_code == 201
    assert resp.data['picture'].startswith('http')
    assert '/pub/' in resp.data['picture']
    assert os.path.exists(os.path.join(settings.MEDIA_ROOT, resp.data['picture'].split('/media/')[1]))


@pytest.mark.django_db
def test_item_update_with_variation(token_client, organizer, event, item):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "variations": [
                {
                    "value": {
                        "de": "Kommentar",
                        "en": "Comment"
                    },
                    "active": True,
                    "description": None,
                    "position": 0,
                    "default_price": None,
                    "price": "23.00"
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Updating add-ons, bundles, or variations via PATCH/PUT is not supported. Please use ' \
                                    'the dedicated nested endpoint."]}'


@pytest.mark.django_db
def test_item_update_with_addon(token_client, organizer, event, item, category):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk),
        {
            "addons": [
                {
                    "addon_category": category.pk,
                    "min_count": 0,
                    "max_count": 10,
                    "position": 0,
                    "multi_allowed": False,
                    "price_included": True
                }
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Updating add-ons, bundles, or variations via PATCH/PUT is not supported. Please use ' \
                                    'the dedicated nested endpoint."]}'


@pytest.mark.django_db
def test_items_delete(token_client, organizer, event, item):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.items.filter(pk=item.id).exists()


@pytest.mark.django_db
def test_items_with_order_position_not_delete(token_client, organizer, event, item, order_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 403
    with scopes_disabled():
        assert event.items.filter(pk=item.id).exists()


@pytest.mark.django_db
def test_items_with_cart_position_delete(token_client, organizer, event, item, cart_position):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.items.filter(pk=item.id).exists()


@pytest.fixture
def variations(item):
    v = []
    v.append(item.variations.create(value="ChildA1"))
    v.append(item.variations.create(value="ChildA2"))
    return v


@pytest.fixture
def variations2(item2):
    v = []
    v.append(item2.variations.create(value="ChildB1"))
    v.append(item2.variations.create(value="ChildB2"))
    return v


@pytest.fixture
def variation(item):
    return item.variations.create(value="ChildC1")


TEST_VARIATIONS_RES = {
    "value": {
        "en": "ChildC1"
    },
    "active": True,
    "description": None,
    "position": 0,
    "default_price": None,
    "price": "23.00",
    "checkin_attention": False,
    "checkin_text": None,
    "require_approval": False,
    "require_membership": False,
    "require_membership_hidden": False,
    "require_membership_types": [],
    "all_sales_channels": True,
    "limit_sales_channels": [],
    "available_from": None,
    "available_until": None,
    "available_from_mode": "hide",
    "available_until_mode": "hide",
    "hide_without_voucher": False,
    "original_price": None,
    "free_price_suggestion": None,
    "meta_data": {}
}

TEST_VARIATIONS_UPDATE = {
    "value": {
        "en": "ChildC2"
    },
    "active": True,
    "description": None,
    "position": 1,
    "default_price": "20.0",
    "checkin_attention": False,
    "checkin_text": None,
    "require_approval": False,
    "require_membership": False,
    "require_membership_hidden": False,
    "require_membership_types": [],
    "sales_channels": ["web"],
    "all_sales_channels": False,
    "limit_sales_channels": ["web"],
    "available_from": None,
    "available_until": None,
    "available_from_mode": "hide",
    "available_until_mode": "hide",
    "hide_without_voucher": False,
    "original_price": None,
    "free_price_suggestion": None,
    "meta_data": {}
}


@pytest.mark.django_db
def test_variations_list(token_client, organizer, event, item, variation):
    res = dict(TEST_VARIATIONS_RES)
    res["id"] = variation.pk
    with scopes_disabled():
        res["sales_channels"] = sorted(organizer.sales_channels.values_list("identifier", flat=True))
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/variations/'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 200
    assert res['value'] == resp.data['results'][0]['value']
    assert res['position'] == resp.data['results'][0]['position']
    assert res['price'] == resp.data['results'][0]['price']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/variations/?active=true'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 200
    assert res['value'] == resp.data['results'][0]['value']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/?active=false'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 200
    assert [] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/variations/?search=Child'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 200
    assert res['value'] == resp.data['results'][0]['value']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/variations/?search=Incorrect'.format(organizer.slug, event.slug, item.pk))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_variations_detail(token_client, organizer, event, item, variation):
    res = dict(TEST_VARIATIONS_RES)
    res["id"] = variation.pk
    with scopes_disabled():
        res["sales_channels"] = sorted(organizer.sales_channels.values_list("identifier", flat=True))
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_variations_create(token_client, organizer, event, item, variation):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/'.format(organizer.slug, event.slug, item.pk),
        {
            "value": {
                "en": "ChildC2"
            },
            "active": True,
            "description": None,
            "position": 1,
            "default_price": None,
            "original_price": "23.42",
            "price": 23.0,
            "meta_data": {
                "day": "Wednesday",
            },
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        var = ItemVariation.objects.get(pk=resp.data['id'])
    assert var.position == 1
    assert var.price == 23.0
    assert var.all_sales_channels
    with scopes_disabled():
        assert not var.limit_sales_channels.exists()
    assert var.meta_data == {"day": "Wednesday"}


@pytest.mark.django_db
def test_variations_create_not_allowed(token_client, organizer, event, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/'.format(organizer.slug, event.slug, item.pk),
        {
            "value": {
                "en": "ChildC2"
            },
            "active": True,
            "description": None,
            "position": 1,
            "default_price": None,
            "price": 23.0
        },
        format='json'
    )
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"This variation cannot be created because the item does ' \
                                    'not have variations. Changing a product without variations to a product with ' \
                                    'variations is not allowed."}'


@pytest.mark.django_db
def test_variations_update(token_client, organizer, event, item, item3, variation):
    res = dict(TEST_VARIATIONS_UPDATE)
    res["id"] = variation.pk
    res["price"] = "20.00"
    res["default_price"] = "20.00"
    res["original_price"] = "50.00"
    res["meta_data"] = {"day": "Thursday"}
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk),
        {
            "value": {
                "en": "ChildC2"
            },
            "position": 1,
            "sales_channels": ["web"],
            "default_price": "20.00",
            "original_price": "50.00",
            "meta_data": {
                "day": "Thursday",
            },
        },
        format='json'
    )
    assert resp.status_code == 200
    assert res == resp.data

    # Variation exists but do not belong to item
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item3.pk, variation.pk),
        {
            "position": 1
        },
        format='json'
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_variations_delete(token_client, organizer, event, item, variations, order):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variations[0].pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not item.variations.filter(pk=variations[0].pk).exists()


@pytest.mark.django_db
def test_variations_with_order_position_not_delete(token_client, organizer, event, item, order, variations, order_position):
    with scopes_disabled():
        assert item.variations.filter(pk=variations[0].id).exists()
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variations[0].pk))
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"This variation cannot be deleted because it has already been ordered ' \
                                    'by a user or currently is in a users\'s cart. Please set the variation as ' \
                                    '\'inactive\' instead."}'
    with scopes_disabled():
        assert item.variations.filter(pk=variations[0].id).exists()


@pytest.mark.django_db
def test_variations_with_cart_position_not_delete(token_client, organizer, event, item, variations, cart_position):
    with scopes_disabled():
        assert item.variations.filter(pk=variations[0].id).exists()
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variations[0].pk))
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"This variation cannot be deleted because it has already been ordered ' \
                                    'by a user or currently is in a users\'s cart. Please set the variation as ' \
                                    '\'inactive\' instead."}'
    with scopes_disabled():
        assert item.variations.filter(pk=variations[0].id).exists()


@pytest.mark.django_db
def test_only_variation_not_delete(token_client, organizer, event, item, variation):
    with scopes_disabled():
        assert item.variations.filter(pk=variation.id).exists()
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/variations/{}/'.format(organizer.slug, event.slug, item.pk, variation.pk))
    assert resp.status_code == 403
    assert resp.content.decode() == '{"detail":"This variation cannot be deleted because it is the only variation. ' \
                                    'Changing a product with variations to a product without variations is not ' \
                                    'allowed."}'
    with scopes_disabled():
        assert item.variations.filter(pk=variation.id).exists()


@pytest.fixture
def bundle(item, item3, category):
    return item.bundles.create(bundled_item=item3, count=1, designated_price=2)


TEST_BUNDLE_RES = {
    "bundled_item": 0,
    "bundled_variation": None,
    "count": 1,
    "designated_price": "2.00"
}


@pytest.mark.django_db
def test_bundles_list(token_client, organizer, event, item, bundle, item3):
    res = dict(TEST_BUNDLE_RES)
    res["id"] = bundle.pk
    res["bundled_item"] = item3.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/bundles/'.format(organizer.slug, event.slug,
                                                                                       item.pk))
    assert resp.status_code == 200
    assert res == resp.data['results'][0]


@pytest.mark.django_db
def test_bundles_detail(token_client, organizer, event, item, bundle, item3):
    res = dict(TEST_BUNDLE_RES)
    res["id"] = bundle.pk
    res["bundled_item"] = item3.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/bundles/{}/'.format(organizer.slug, event.slug,
                                                                                          item.pk, bundle.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_bundles_create(token_client, organizer, event, item, item2, item3):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/bundles/'.format(organizer.slug, event.slug, item.pk),
        {
            "bundled_item": item3.pk,
            "bundled_variation": None,
            "count": 1,
            "designated_price": "1.50",
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        b = ItemBundle.objects.get(pk=resp.data['id'])
    assert b.bundled_item == item3
    assert b.bundled_variation is None
    assert b.designated_price == 1.5
    assert b.count == 1

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/bundles/'.format(organizer.slug, event.slug, item.pk),
        {
            "bundled_item": item2.pk,
            "bundled_variation": None,
            "count": 1,
            "designated_price": "1.50",
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The bundled item must belong to the same event as the item."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/bundles/'.format(organizer.slug, event.slug, item.pk),
        {
            "bundled_item": item.pk,
            "bundled_variation": None,
            "count": 1,
            "designated_price": "1.50",
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The bundled item must not be the same item as the bundling one."]}'

    with scopes_disabled():
        item3.bundles.create(bundled_item=item, count=1, designated_price=3)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/bundles/'.format(organizer.slug, event.slug, item.pk),
        {
            "bundled_item": item3.pk,
            "bundled_variation": None,
            "count": 1,
            "designated_price": "1.50",
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The bundled item must not have bundles on its own."]}'


@pytest.mark.django_db
def test_bundles_update(token_client, organizer, event, item, bundle):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/bundles/{}/'.format(organizer.slug, event.slug, item.pk, bundle.pk),
        {
            "count": 3,
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        a = ItemBundle.objects.get(pk=bundle.pk)
    assert a.count == 3


@pytest.mark.django_db
def test_bundles_delete(token_client, organizer, event, item, bundle):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/bundles/{}/'.format(organizer.slug, event.slug,
                                                                                             item.pk, bundle.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not item.bundles.filter(pk=bundle.id).exists()


@pytest.fixture
def addon(item, category):
    return item.addons.create(addon_category=category, min_count=0, max_count=10, position=1)


@pytest.fixture
def option(question):
    return question.options.create(answer='XL', identifier='LVETRWVU')


TEST_ADDONS_RES = {
    "min_count": 0,
    "max_count": 10,
    "position": 1,
    "multi_allowed": False,
    "price_included": False
}


@pytest.mark.django_db
def test_addons_list(token_client, organizer, event, item, addon, category):
    res = dict(TEST_ADDONS_RES)
    res["id"] = addon.pk
    res["addon_category"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug,
                                                                                      item.pk))
    assert resp.status_code == 200
    assert res['addon_category'] == resp.data['results'][0]['addon_category']
    assert res['min_count'] == resp.data['results'][0]['min_count']
    assert res['max_count'] == resp.data['results'][0]['max_count']
    assert res['position'] == resp.data['results'][0]['position']


@pytest.mark.django_db
def test_addons_detail(token_client, organizer, event, item, addon, category):
    res = dict(TEST_ADDONS_RES)
    res["id"] = addon.pk
    res["addon_category"] = category.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug,
                                                                                         item.pk, addon.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_addons_create(token_client, organizer, event, item, category, category2):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug, item.pk),
        {
            "addon_category": category.pk,
            "min_count": 0,
            "max_count": 10,
            "position": 1,
            "multi_allowed": False,
            "price_included": False
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        addon = ItemAddOn.objects.get(pk=resp.data['id'])
    assert addon.position == 1
    assert addon.addon_category == category

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug, item.pk),
        {
            "addon_category": category.pk,
            "min_count": 10,
            "max_count": 20,
            "position": 2,
            "multi_allowed": False,
            "price_included": False
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"addon_category":["The item already has an add-on of this category."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/'.format(organizer.slug, event.slug, item.pk),
        {
            "addon_category": category2.pk,
            "min_count": 10,
            "max_count": 20,
            "position": 2,
            "multi_allowed": False,
            "price_included": False
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"addon_category":["The add-on\'s category must belong to the same event as ' \
                                    'the item."]}'


@pytest.mark.django_db
def test_addons_update(token_client, organizer, event, item, addon):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug, item.pk, addon.pk),
        {
            "min_count": 100,
            "max_count": 101
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        a = ItemAddOn.objects.get(pk=addon.pk)
    assert a.min_count == 100
    assert a.max_count == 101

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug, item.pk, a.pk),
        {
            "min_count": 10,
            "max_count": 1
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The maximum count needs to be greater than the minimum ' \
                                    'count."]}'


@pytest.mark.django_db
def test_addons_delete(token_client, organizer, event, item, addon):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/items/{}/addons/{}/'.format(organizer.slug, event.slug,
                                                                                            item.pk, addon.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not item.addons.filter(pk=addon.id).exists()


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(item)
    return q


TEST_QUOTA_RES = {
    "name": "Budget Quota",
    "size": 200,
    "items": [],
    "variations": [],
    "subevent": None,
    "close_when_sold_out": False,
    "release_after_exit": False,
    "closed": False,
    "ignore_for_event_availability": False,
}


@pytest.mark.django_db
def test_quota_list(token_client, organizer, event, quota, item, item3, subevent):
    quota.items.add(item3)
    res = dict(TEST_QUOTA_RES)
    res["id"] = quota.pk
    res["items"] = [item.pk, item3.pk]

    resp = token_client.get('/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    quota.subevent = subevent
    quota.save()
    res["subevent"] = subevent.pk
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/quotas/?subevent={}'.format(organizer.slug, event.slug, subevent.pk))
    assert [res] == resp.data['results']
    with scopes_disabled():
        se2 = event.subevents.create(name="Foobar", date_from=datetime(2017, 12, 27, 10, 0, 0, tzinfo=timezone.utc))
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/quotas/?subevent={}'.format(organizer.slug, event.slug, se2.pk))
    assert [] == resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/quotas/?items__in={},{},0'.format(organizer.slug, event.slug, item.pk, item3.pk))
    assert [res] == resp.data['results']
    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/quotas/?items__in=0'.format(organizer.slug, event.slug))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_quota_detail(token_client, organizer, event, quota, item):
    res = dict(TEST_QUOTA_RES)

    res["id"] = quota.pk
    res["items"] = [item.pk]
    resp = token_client.get('/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug,
                                                                                quota.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_quota_create(token_client, organizer, event, event2, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        quota = Quota.objects.get(pk=resp.data['id'])
    assert quota.name == "Ticket Quota"
    assert quota.size == 200

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event2.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more items do not belong to this event."]}'


@pytest.mark.django_db
def test_quota_create_with_variations(token_client, organizer, event, item, variations, variations2):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 201

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [100],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"variations":["Invalid pk \\"100\\" - object does not exist."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk, variations2[0].pk],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["All variations must belong to an item contained in the items list."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more items has variations but none of these are in the variations list."]}'


@pytest.mark.django_db
def test_quota_create_with_subevent(token_client, organizer, event, event3, item, variations, subevent, subevent2):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": subevent.pk
        },
        format='json'
    )
    assert resp.status_code == 201

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Subevent cannot be null for event series."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [item.pk],
            "variations": [variations[0].pk],
            "subevent": subevent2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The subevent does not belong to this event."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/quotas/'.format(organizer.slug, event3.slug),
        {
            "name": "Ticket Quota",
            "size": 200,
            "items": [],
            "variations": [],
            "subevent": subevent2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["The subevent does not belong to this event."]}'


@pytest.mark.django_db
def test_quota_update(token_client, organizer, event, quota, item):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug, quota.pk),
        {
            "name": "Ticket Quota Update",
            "size": 111,
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        quota = Quota.objects.get(pk=resp.data['id'])
    assert quota.name == "Ticket Quota Update"
    assert quota.size == 111
    assert quota.all_logentries().count() == 1


@pytest.mark.django_db
def test_quota_update_closed(token_client, organizer, event, quota, item):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug, quota.pk),
        {
            "closed": True,
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        quota = Quota.objects.get(pk=resp.data['id'])
    assert quota.all_logentries().filter(action_type="pretix.event.quota.closed").count() == 1
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug, quota.pk),
        {
            "closed": False,
        },
        format='json'
    )
    assert resp.status_code == 200
    assert quota.all_logentries().filter(action_type="pretix.event.quota.opened").count() == 1


@pytest.mark.django_db
def test_quota_update_unchanged(token_client, organizer, event, quota, item):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug, quota.pk),
        {
            "size": 200,
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        quota = Quota.objects.get(pk=resp.data['id'])
    assert quota.size == 200
    assert quota.all_logentries().count() == 0


@pytest.mark.django_db
def test_quota_delete(token_client, organizer, event, quota):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/quotas/{}/'.format(organizer.slug, event.slug, quota.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.quotas.filter(pk=quota.id).exists()


@pytest.mark.django_db
def test_quota_availability(token_client, organizer, event, quota, item):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/quotas/{}/availability/'.format(
        organizer.slug, event.slug, quota.pk))
    assert resp.status_code == 200
    assert {'blocking_vouchers': 0,
            'available_number': 200,
            'pending_orders': 0,
            'exited_orders': 0,
            'cart_positions': 0,
            'available': True,
            'total_size': 200,
            'paid_orders': 0,
            'waiting_list': 0} == resp.data


@pytest.fixture
def question(event, item):
    q = event.questions.create(
        question="T-Shirt size", type="C", identifier="ABC", help_text="This is an example question"
    )
    q.items.add(item)
    q.options.create(answer="XL", identifier="LVETRWVU")
    return q


TEST_QUESTION_RES = {
    "question": {"en": "T-Shirt size"},
    "type": "C",
    "required": False,
    "items": [],
    "ask_during_checkin": False,
    "show_during_checkin": False,
    "hidden": False,
    "print_on_invoice": False,
    "identifier": "ABC",
    "position": 0,
    "dependency_question": None,
    "dependency_value": None,
    "dependency_values": [],
    "valid_number_min": None,
    "valid_number_max": None,
    "valid_date_min": None,
    "valid_date_max": None,
    "valid_datetime_min": None,
    "valid_datetime_max": None,
    "valid_file_portrait": False,
    "valid_string_length_max": None,
    "help_text": {"en": "This is an example question"},
    "options": [
        {
            "id": 0,
            "position": 0,
            "identifier": "LVETRWVU",
            "answer": {"en": "XL"}
        }
    ]
}


@pytest.mark.django_db
def test_question_list(token_client, organizer, event, question, item):
    res = dict(TEST_QUESTION_RES)
    res["id"] = question.pk
    res["items"] = [item.pk]
    res["options"][0]["id"] = question.options.first().pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/?required=false'.format(
        organizer.slug, event.slug
    ))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/?ask_during_checkin=false'.format(
        organizer.slug, event.slug
    ))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/?identifier=ABC'.format(
        organizer.slug, event.slug
    ))
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/?required=true'.format(
        organizer.slug, event.slug
    ))
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/?ask_during_checkin=true'.format(
        organizer.slug, event.slug
    ))
    assert [] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/?identifier=DEF'.format(
        organizer.slug, event.slug
    ))
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_question_detail(token_client, organizer, event, question, item):
    res = dict(TEST_QUESTION_RES)

    res["id"] = question.pk
    res["items"] = [item.pk]
    res["options"][0]["id"] = question.options.first().pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug,
                                                                                   question.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_question_create(token_client, organizer, event, event2, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "identifier": None
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        question = Question.objects.get(pk=resp.data['id'])
        assert question.question == "What's your name?"
        assert question.type == "S"
        assert question.identifier is not None
        assert len(question.items.all()) == 1

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event2.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "identifier": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["One or more items do not belong to this event."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "identifier": question.identifier
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"identifier":["This identifier is already used for a different question."]}'

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "dependency_question": question.pk,
            "dependency_value": "1",
            "identifier": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"dependency_question":["Question dependencies can only be set to boolean or choice questions."]}'

    question.type = Question.TYPE_BOOLEAN
    question.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": True,
            "dependency_question": question.pk,
            "dependency_value": "1",
            "identifier": None
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Dependencies are not supported during check-in."]}'

    question.type = Question.TYPE_BOOLEAN
    question.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "dependency_question": question.pk,
            "dependency_value": "1",
            "identifier": None
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        q2 = Question.objects.get(pk=resp.data['id'])
    assert q2.dependency_question == question

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "identifier": None,
            "dependency_question": None,
            "dependency_values": [],
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        question = Question.objects.get(pk=resp.data['id'])
        assert question.question == "What's your name?"
        assert question.type == "S"
        assert question.identifier is not None
        assert len(question.items.all()) == 1
        assert question.dependency_question is None
        assert question.dependency_values == []


@pytest.mark.django_db
def test_question_update(token_client, organizer, event, question):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "question": "What's your shoe size?",
            "type": "N",
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        question = Question.objects.get(pk=resp.data['id'])
    assert question.question == "What's your shoe size?"
    assert question.type == "N"


@pytest.mark.django_db
def test_question_update_type_changes(token_client, organizer, event, question):
    # Allowed because no answers exist
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "type": "B",
        },
        format='json'
    )
    assert resp.status_code == 200

    with scopes_disabled():
        question.answers.create(answer="12")

    # Allowed change
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "type": "S",
        },
        format='json'
    )
    assert resp.status_code == 200

    # Forbidden change
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "type": "B",
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == ('{"type":["The system already contains answers to this question that are not '
                                     'compatible with changing the type of question without data loss. Consider hiding '
                                     'this question and creating a new one instead."]}')


@pytest.mark.django_db
def test_question_update_circular_dependency(token_client, organizer, event, question):
    with scopes_disabled():
        q2 = event.questions.create(question="T-Shirt size", type="B", identifier="FOO", dependency_question=question)
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "dependency_question": q2.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Circular dependency between questions detected."]}'


@pytest.mark.django_db
def test_question_self_dependency(token_client, organizer, event, question):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "dependency_question": question.pk
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"dependency_question":["A question cannot depend on itself."]}'


@pytest.mark.django_db
def test_question_update_options(token_client, organizer, event, question, item):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "options": [
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"non_field_errors":["Updating options via PATCH/PUT is not supported. Please use the dedicated nested endpoint."]}'


@pytest.mark.django_db
def test_question_delete(token_client, organizer, event, question):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.questions.filter(pk=question.id).exists()


@pytest.mark.django_db
def test_question_update_dependency_values(token_client, organizer, event, question):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "dependency_values": ["a", "b"]
        },
        format='json'
    )
    assert resp.status_code == 200
    question.refresh_from_db()
    assert question.dependency_values == ["a", "b"]


@pytest.mark.django_db
def test_question_update_dependency_value_legacy(token_client, organizer, event, question):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "dependency_value": "a"
        },
        format='json'
    )
    assert resp.status_code == 200
    question.refresh_from_db()
    assert question.dependency_values == ["a"]


@pytest.mark.django_db
def test_question_update_dependency_value_legacy_conflict(token_client, organizer, event, question):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/'.format(organizer.slug, event.slug, question.pk),
        {
            "dependency_values": ["a", "b"],
            "dependency_value": "a"
        },
        format='json'
    )
    assert resp.status_code == 200
    question.refresh_from_db()
    assert question.dependency_values == ["a"]


TEST_OPTIONS_RES = {
    "identifier": "LVETRWVU",
    "answer": {"en": "XL"},
    "position": 0
}


@pytest.mark.django_db
def test_options_list(token_client, organizer, event, question, option):
    res = dict(TEST_OPTIONS_RES)
    res["id"] = option.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/{}/options/'.format(
        organizer.slug, event.slug, question.pk)
    )
    assert resp.status_code == 200
    assert res['identifier'] == resp.data['results'][0]['identifier']
    assert res['answer'] == resp.data['results'][0]['answer']


@pytest.mark.django_db
def test_options_detail(token_client, organizer, event, question, option):
    res = dict(TEST_OPTIONS_RES)
    res["id"] = option.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/questions/{}/options/{}/'.format(
        organizer.slug, event.slug, question.pk, option.pk
    ))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_options_create(token_client, organizer, event, question):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/{}/options/'.format(organizer.slug, event.slug, question.pk),
        {
            "identifier": "DFEMJWMJ",
            "answer": "A",
            "position": 0
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        option = QuestionOption.objects.get(pk=resp.data['id'])
    assert option.answer == "A"

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/{}/options/'.format(organizer.slug, event.slug, question.pk),
        {
            "identifier": "DFEMJWMJ",
            "answer": "A",
            "position": 0
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"identifier":["The identifier \\"DFEMJWMJ\\" is already used for a different option."]}'


@pytest.mark.django_db
def test_options_update(token_client, organizer, event, question, option):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/questions/{}/options/{}/'.format(organizer.slug, event.slug, question.pk, option.pk),
        {
            "answer": "B",
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        a = QuestionOption.objects.get(pk=option.pk)
    assert a.answer == "B"


@pytest.mark.django_db
def test_options_delete(token_client, organizer, event, question, option):
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/questions/{}/options/{}/'.format(
        organizer.slug, event.slug, question.pk, option.pk
    ))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not question.options.filter(pk=option.id).exists()


@pytest.mark.django_db
def test_question_create_with_option(token_client, organizer, event, item):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "identifier": None,
            "options": [
                {
                    "identifier": None,
                    "answer": {"en": "A"},
                    "position": 0,
                },
                {
                    "identifier": None,
                    "answer": {"en": "B"},
                    "position": 1,
                },
            ]
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        question = Question.objects.get(pk=resp.data['id'])
        assert str(question.options.first().answer) == "A"
        assert question.options.first().identifier is not None
        assert str(question.options.last().answer) == "B"
        assert 2 == question.options.count()

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/questions/'.format(organizer.slug, event.slug),
        {
            "question": "What's your name?",
            "type": "S",
            "required": True,
            "items": [item.pk],
            "position": 0,
            "ask_during_checkin": False,
            "identifier": None,
            "options": [
                {
                    "identifier": "ABC",
                    "answer": {"en": "A"},
                    "position": 0,
                },
                {
                    "identifier": "ABC",
                    "answer": {"en": "B"},
                    "position": 1,
                },
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.content.decode() == '{"options":["The identifier \\"ABC\\" is already used for a different option."]}'
