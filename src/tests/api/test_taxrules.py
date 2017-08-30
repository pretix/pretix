import pytest

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
