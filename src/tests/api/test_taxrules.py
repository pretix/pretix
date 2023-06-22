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
from decimal import Decimal

import pytest
from django_scopes import scopes_disabled

from pretix.base.models import TaxRule

TEST_TAXRULE_RES = {
    'internal_name': None,
    'keep_gross_if_rate_changes': False,
    'name': {'en': 'VAT'},
    'rate': '19.00',
    'price_includes_tax': True,
    'eu_reverse_charge': False,
    'home_country': '',
    'custom_rules': None,
}


@pytest.mark.django_db
def test_rule_list(token_client, organizer, event, taxrule):
    res = dict(TEST_TAXRULE_RES)
    res["id"] = taxrule.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/taxrules/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_rule_detail(token_client, organizer, event, taxrule):
    res = dict(TEST_TAXRULE_RES)
    res["id"] = taxrule.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/taxrules/{}/'.format(organizer.slug, event.slug,
                                                                                  taxrule.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_rule_create(token_client, organizer, event):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/taxrules/'.format(organizer.slug, event.slug),
        {
            "name": {"en": "VAT", "de": "MwSt"},
            "rate": "19.00",
            "price_includes_tax": True,
            "eu_reverse_charge": False,
            "home_country": "DE"
        },
        format='json'
    )
    assert resp.status_code == 201
    rule = TaxRule.objects.get(pk=resp.data['id'])
    assert rule.name.data == {"en": "VAT", "de": "MwSt"}
    assert rule.rate == Decimal("19.00")
    assert rule.price_includes_tax is True
    assert rule.eu_reverse_charge is False
    assert str(rule.home_country) == "DE"


@pytest.mark.django_db
def test_rule_update(token_client, organizer, event, taxrule):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/taxrules/{}/'.format(organizer.slug, event.slug, taxrule.pk),
        {
            "rate": "20.00",
            "custom_rules": [
                {"country": "AT", "address_type": "", "action": "vat", "rate": "19.00",
                 "invoice_text": {"en": "Austrian VAT applies"}}
            ]
        },
        format='json'
    )
    assert resp.status_code == 200
    taxrule.refresh_from_db()
    assert taxrule.rate == Decimal("20.00")
    assert taxrule.all_logentries().last().action_type == 'pretix.event.taxrule.changed'


@pytest.mark.django_db
def test_rule_delete(token_client, organizer, event, taxrule):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/taxrules/{}/'.format(organizer.slug, event.slug, taxrule.pk),
    )
    assert resp.status_code == 204
    assert not event.tax_rules.exists()


@pytest.mark.django_db
def test_rule_delete_forbidden(token_client, organizer, event, taxrule):
    with scopes_disabled():
        event.items.create(name="Budget Ticket", default_price=23, tax_rule=taxrule)
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/taxrules/{}/'.format(organizer.slug, event.slug, taxrule.pk),
    )
    assert resp.status_code == 403
    assert event.tax_rules.exists()


@pytest.mark.django_db
def test_rule_update_invalid_rules(token_client, organizer, event, taxrule):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/taxrules/{}/'.format(organizer.slug, event.slug, taxrule.pk),
        {
            "custom_rules": [
                {"foo": "bar"}
            ]
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data["custom_rules"][0].startswith(
        "Your set of rules is not valid. Error message: 'country' is a required property"
    )
