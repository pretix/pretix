"""
Tests for TwilioWebhookView (STOP/START opt-in/opt-out handling).
"""
import pytest
from django_scopes import scopes_disabled

from pretix.base.models import Customer, Organizer
from pretix_twilio_sms.models import CustomerSmsPreference


TEST_PHONE = "+15551234567"


@pytest.fixture(autouse=True)
def disable_twilio_webhook_signature(monkeypatch):
    """
    Disable Twilio signature validation in tests so POSTs are accepted.
    test_webhook_invalid_signature_returns_403 overrides this to test 403.
    """
    monkeypatch.setattr(
        "pretix_twilio_sms.views._get_webhook_auth_token",
        lambda: "",
    )


@pytest.fixture
@scopes_disabled()
def organizer():
    return Organizer.objects.create(name="Test Org", slug="testorg")


@pytest.fixture
@scopes_disabled()
def customer_with_phone(organizer):
    return organizer.customers.create(
        email="user@example.com",
        password="test",
        is_active=True,
        is_verified=True,
        phone=TEST_PHONE,
    )


def _post_webhook(client, From=TEST_PHONE, OptOutType="STOP"):
    """POST to Twilio webhook with form-urlencoded data."""
    return client.post(
        "/_twilio_sms/webhook/",
        data={"From": From, "OptOutType": OptOutType},
    )


@pytest.mark.django_db
def test_webhook_stop_creates_preference_with_opt_out(customer_with_phone, client):
    """STOP creates CustomerSmsPreference with sms_opt_in=False."""
    response = _post_webhook(client, OptOutType="STOP")
    print("POST data:", response.wsgi_request.POST)
    assert response.status_code == 200
    assert "text/xml" in response["Content-Type"]
    assert "<Response></Response>" in response.content.decode()

    pref = CustomerSmsPreference.objects.get(customer=customer_with_phone)
    assert pref.sms_opt_in is False


@pytest.mark.django_db
def test_webhook_start_creates_preference_with_opt_in(customer_with_phone, client):
    """START creates CustomerSmsPreference with sms_opt_in=True."""
    response = _post_webhook(client, OptOutType="START")
    assert response.status_code == 200

    pref = CustomerSmsPreference.objects.get(customer=customer_with_phone)
    assert pref.sms_opt_in is True


@pytest.mark.django_db
def test_webhook_stop_updates_existing_preference(customer_with_phone, client):
    """STOP updates existing CustomerSmsPreference from True to False."""
    CustomerSmsPreference.objects.create(customer=customer_with_phone, sms_opt_in=True)

    response = _post_webhook(client, OptOutType="STOP")
    assert response.status_code == 200

    pref = CustomerSmsPreference.objects.get(customer=customer_with_phone)
    assert pref.sms_opt_in is False


@pytest.mark.django_db
def test_webhook_start_updates_existing_preference(customer_with_phone, client):
    """START updates existing CustomerSmsPreference from False to True."""
    CustomerSmsPreference.objects.create(customer=customer_with_phone, sms_opt_in=False)

    response = _post_webhook(client, OptOutType="START")
    assert response.status_code == 200

    pref = CustomerSmsPreference.objects.get(customer=customer_with_phone)
    assert pref.sms_opt_in is True


@pytest.mark.django_db
def test_webhook_unknown_phone_returns_200(client):
    """Unknown phone returns 200 and empty TwiML (no Customer match)."""
    response = _post_webhook(client, From="+15559999999", OptOutType="STOP")
    assert response.status_code == 200
    assert CustomerSmsPreference.objects.count() == 0


@pytest.mark.django_db
def test_webhook_missing_opt_out_type_returns_200(customer_with_phone, client):
    """Missing OptOutType returns 200, no preference changes."""
    response = _post_webhook(client, OptOutType="")
    assert response.status_code == 200
    assert not CustomerSmsPreference.objects.filter(customer=customer_with_phone).exists()


@pytest.mark.django_db
def test_webhook_help_ignored(customer_with_phone, client):
    """OptOutType HELP returns 200, no preference changes."""
    response = _post_webhook(client, OptOutType="HELP")
    assert response.status_code == 200
    assert not CustomerSmsPreference.objects.filter(customer=customer_with_phone).exists()


@pytest.mark.django_db
def test_webhook_missing_from_returns_200(client):
    """Missing From returns 200 (graceful handling)."""
    response = client.post(
        "/_twilio_sms/webhook/",
        data={"OptOutType": "STOP"},
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_webhook_get_returns_405(client):
    """GET returns 405 Method Not Allowed."""
    response = client.get("/_twilio_sms/webhook/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_webhook_invalid_signature_returns_403(client, monkeypatch):
    """Invalid/missing signature returns 403 when auth token is configured."""
    monkeypatch.setattr(
        "pretix_twilio_sms.views._get_webhook_auth_token",
        lambda: "secret_token",
    )
    response = _post_webhook(client, OptOutType="STOP")
    assert response.status_code == 403


@pytest.mark.django_db
def test_webhook_stop_updates_multiple_customers_same_phone(organizer, client):
    """STOP updates all customers with matching phone across organizers."""
    with scopes_disabled():
        org2 = Organizer.objects.create(name="Other Org", slug="otherorg")
    with scopes_disabled():
        c1 = organizer.customers.create(
            email="a@example.com",
            password="x",
            is_active=True,
            is_verified=True,
            phone=TEST_PHONE,
        )
        c2 = org2.customers.create(
            email="b@example.com",
            password="x",
            is_active=True,
            is_verified=True,
            phone=TEST_PHONE,
        )

    response = _post_webhook(client, OptOutType="STOP")
    assert response.status_code == 200

    pref1 = CustomerSmsPreference.objects.get(customer=c1)
    pref2 = CustomerSmsPreference.objects.get(customer=c2)
    assert pref1.sms_opt_in is False
    assert pref2.sms_opt_in is False