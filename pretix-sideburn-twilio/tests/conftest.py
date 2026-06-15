import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Item, Organizer, Quota
from pretix_twilio_sms import services as twilio_services


TEST_PHONE = "+12125552368"
TEST_EMAIL = "waitlist@example.com"
TEST_PASSWORD = "testpass123"


@pytest.fixture(autouse=True)
def use_dummy_sms_sender():
    """Use dummy SMS sender in tests so we don't hit Twilio."""
    original = twilio_services._sms_sender
    twilio_services._sms_sender = twilio_services.send_waiting_list_sms_dummy
    try:
        yield
    finally:
        twilio_services._sms_sender = original


@pytest.fixture
def sms_calls(monkeypatch):
    """Capture SMS send attempts via the pluggable sender."""
    calls = []

    def _track(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(twilio_services, "_sms_sender", _track)
    return calls


@pytest.fixture
@scopes_disabled()
def twilio_env():
    """
    Organizer + event with Twilio plugin enabled and waiting list active.
    """
    organizer = Organizer.objects.create(name="Sideburn Test", slug="sideburntest")
    organizer.settings.customer_accounts = True
    organizer.settings.customer_accounts_native = True
    organizer.settings.save()

    event = Event.objects.create(
        organizer=organizer,
        name="Test Event",
        slug="testevent",
        date_from=now(),
        live=True,
        plugins="pretix_twilio_sms",
    )
    event.settings.set("waiting_list_enabled", True)

    quota = Quota.objects.create(event=event, name="Tickets", size=0)
    item = Item.objects.create(
        event=event,
        name="General Admission",
        default_price=100,
        admission=True,
        active=True,
    )
    quota.items.add(item)

    customer = organizer.customers.create(
        email=TEST_EMAIL,
        is_verified=True,
        is_active=True,
        phone=TEST_PHONE,
    )
    customer.set_password(TEST_PASSWORD)
    customer.save()

    return {
        "organizer": organizer,
        "event": event,
        "item": item,
        "quota": quota,
        "customer": customer,
    }


@pytest.fixture
def logged_in_customer(client, twilio_env):
    response = client.post(
        "/{}/account/login".format(twilio_env["organizer"].slug),
        {"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 302
    return twilio_env["customer"]
