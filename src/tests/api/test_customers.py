import pytest


@pytest.fixture
def customer(organizer, event):
    return organizer.customers.create(
        identifier="8WSAJCJ",
        email="foo@example.org",
        name_parts={"_legacy": "Foo"},
        name_cached="Foo",
        is_verified=False,
    )


TEST_CUSTOMER_RES = {
    "identifier": "8WSAJCJ",
    "email": "foo@example.org",
    "name": "Foo",
    "name_parts": {
        "_legacy": "Foo",
    },
    "is_active": True,
    "is_verified": False,
    "last_login": None,
    "date_joined": "2021-04-06T13:44:22.809216Z",
    "locale": "en",
    "last_modified": "2021-04-06T13:44:22.809377Z"
}


@pytest.mark.django_db
def test_customer_list(token_client, organizer, event, customer):
    res = dict(TEST_CUSTOMER_RES)
    res["date_joined"] = customer.date_joined.isoformat().replace('+00:00', 'Z')
    res["last_modified"] = customer.last_modified.isoformat().replace('+00:00', 'Z')

    resp = token_client.get('/api/v1/organizers/{}/customers/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_customer_detail(token_client, organizer, event, customer):
    res = dict(TEST_CUSTOMER_RES)
    res["date_joined"] = customer.date_joined.isoformat().replace('+00:00', 'Z')
    res["last_modified"] = customer.last_modified.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/customers/{}/'.format(organizer.slug, customer.identifier))
    assert resp.status_code == 200
    assert res == resp.data
