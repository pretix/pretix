from decimal import Decimal

import pytest
from django_scopes import scopes_disabled

from pretix.base.models import TaxRule

TEST_TAXRULE_RES = {
    'name': {'en': 'VAT'},
    'rate': '19.00',
    'price_includes_tax': True,
    'eu_reverse_charge': False,
    'home_country': ''
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
