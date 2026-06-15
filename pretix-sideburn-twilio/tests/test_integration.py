"""
Integration tests for pretix-sideburn-twilio hooks and waiting-list SMS flow.

Run from the monorepo:
    cd src && pytest ../pretix-sideburn-twilio/tests/test_integration.py -v
"""
import pytest
from django_scopes import scope, scopes_disabled

from pretix.base.models import WaitingListEntry
from pretix_twilio_sms.models import CustomerSmsPreference

TEST_PHONE = "+12125552368"
TEST_EMAIL = "waitlist@example.com"


@pytest.mark.django_db
def test_waitinglist_signup_with_sms_opt_in(client, twilio_env, logged_in_customer):
    event = twilio_env["event"]
    item = twilio_env["item"]
    organizer = twilio_env["organizer"]

    response = client.post(
        "/{}/{}/waitinglist/?item={}".format(organizer.slug, event.slug, item.pk),
        {
            "email": TEST_EMAIL,
            "itemvar": str(item.pk),
            "sms_opt_in": "on",
            "sms_phone_0": "+1",
            "sms_phone_1": "2125552368",
        },
    )
    assert response.status_code == 302

    with scopes_disabled():
        entry = WaitingListEntry.objects.get(event=event, email=TEST_EMAIL)
        pref = CustomerSmsPreference.objects.get(customer=logged_in_customer)

    assert entry.phone
    assert pref.sms_opt_in is True
    assert str(logged_in_customer.phone) == TEST_PHONE


@pytest.mark.django_db
def test_waitinglist_signup_opt_out(client, twilio_env, logged_in_customer):
    event = twilio_env["event"]
    item = twilio_env["item"]
    organizer = twilio_env["organizer"]

    response = client.post(
        "/{}/{}/waitinglist/?item={}".format(organizer.slug, event.slug, item.pk),
        {
            "email": TEST_EMAIL,
            "itemvar": str(item.pk),
        },
    )
    assert response.status_code == 302

    with scopes_disabled():
        pref = CustomerSmsPreference.objects.get(customer=logged_in_customer)
    assert pref.sms_opt_in is False


@pytest.mark.django_db
def test_send_voucher_queues_sms_when_opted_in(twilio_env, sms_calls):
    event = twilio_env["event"]
    item = twilio_env["item"]
    customer = twilio_env["customer"]

    CustomerSmsPreference.objects.create(customer=customer, sms_opt_in=True)

    with scope(organizer=event.organizer):
        entry = WaitingListEntry.objects.create(
            event=event,
            item=item,
            email=TEST_EMAIL,
            phone=TEST_PHONE,
        )
        entry.send_voucher()

    assert len(sms_calls) == 1
    assert sms_calls[0]["sms_opt_in"] is True
    assert sms_calls[0]["phone"] == TEST_PHONE
    assert sms_calls[0]["entry_id"] == entry.pk


@pytest.mark.django_db
def test_send_voucher_skips_sms_when_opted_out(twilio_env, sms_calls):
    event = twilio_env["event"]
    item = twilio_env["item"]
    customer = twilio_env["customer"]

    CustomerSmsPreference.objects.create(customer=customer, sms_opt_in=False)

    with scope(organizer=event.organizer):
        entry = WaitingListEntry.objects.create(
            event=event,
            item=item,
            email=TEST_EMAIL,
            phone=TEST_PHONE,
        )
        entry.send_voucher()

    assert len(sms_calls) == 0


@pytest.mark.django_db
def test_send_voucher_skips_sms_without_phone(twilio_env, sms_calls):
    event = twilio_env["event"]
    item = twilio_env["item"]
    customer = twilio_env["customer"]
    customer.phone = None
    customer.save(update_fields=["phone"])

    CustomerSmsPreference.objects.create(customer=customer, sms_opt_in=True)

    with scope(organizer=event.organizer):
        entry = WaitingListEntry.objects.create(
            event=event,
            item=item,
            email=TEST_EMAIL,
        )
        entry.send_voucher()

    assert len(sms_calls) == 0


@pytest.mark.django_db
def test_customer_profile_shows_sms_opt_in_status(client, twilio_env, logged_in_customer):
    CustomerSmsPreference.objects.create(customer=logged_in_customer, sms_opt_in=True)
    organizer = twilio_env["organizer"]

    response = client.get("/{}/account/".format(organizer.slug))
    assert response.status_code == 200
    assert "signed up to receive SMS updates" in response.content.decode()


@pytest.mark.django_db
def test_customer_profile_shows_sms_opt_out_status(client, twilio_env, logged_in_customer):
    CustomerSmsPreference.objects.create(customer=logged_in_customer, sms_opt_in=False)
    organizer = twilio_env["organizer"]

    response = client.get("/{}/account/".format(organizer.slug))
    assert response.status_code == 200
    assert "not signed up to receive SMS updates" in response.content.decode()


@pytest.mark.django_db
def test_change_account_form_saves_sms_preference(client, twilio_env, logged_in_customer):
    organizer = twilio_env["organizer"]
    customer = logged_in_customer

    response = client.post(
        "/{}/account/change".format(organizer.slug),
        {
            "name_parts_0": customer.name or "Test User",
            "email": TEST_EMAIL,
            "phone_0": TEST_PHONE,
            "sms_opt_in": "on",
        },
    )
    assert response.status_code == 302

    pref = CustomerSmsPreference.objects.get(customer=customer)
    assert pref.sms_opt_in is True


@pytest.mark.django_db
def test_admin_path_send_voucher_queues_sms(twilio_env, sms_calls):
    """Direct send_voucher call mirrors control/admin assignment paths."""
    event = twilio_env["event"]
    item = twilio_env["item"]
    customer = twilio_env["customer"]
    CustomerSmsPreference.objects.create(customer=customer, sms_opt_in=True)

    with scope(organizer=event.organizer):
        entry = WaitingListEntry.objects.create(
            event=event,
            item=item,
            email=TEST_EMAIL,
        )
        entry.send_voucher()

    assert len(sms_calls) == 1
    assert sms_calls[0]["entry_id"] == entry.pk
