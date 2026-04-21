from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from django_scopes import scopes_disabled

from pretix.base.models import Organizer
from pretix_twilio_sms.models import CustomerSmsPreference


@pytest.fixture
@scopes_disabled()
def organizer():
    return Organizer.objects.create(name="Purge Test Org", slug="purgetestorg")


@scopes_disabled()
def _create_customer(organizer, email):
    return organizer.customers.create(
        email=email,
        password="test",
        is_active=True,
        is_verified=True,
        phone="+15551234567",
    )


@pytest.mark.django_db
def test_purge_old_sms_preferences_dry_run_does_not_delete(organizer):
    old_customer = _create_customer(organizer, "old@example.com")
    recent_customer = _create_customer(organizer, "recent@example.com")

    old_pref = CustomerSmsPreference.objects.create(
        customer=old_customer,
        sms_opt_in=True,
    )
    recent_pref = CustomerSmsPreference.objects.create(
        customer=recent_customer,
        sms_opt_in=True,
    )

    now = timezone.now()
    CustomerSmsPreference.objects.filter(pk=old_pref.pk).update(
        last_changed=now - timedelta(days=733)
    )
    CustomerSmsPreference.objects.filter(pk=recent_pref.pk).update(
        last_changed=now - timedelta(days=10)
    )

    out = StringIO()
    call_command("purge_old_sms_preferences", "--dry-run", stdout=out)

    assert "would be deleted" in out.getvalue()
    assert CustomerSmsPreference.objects.filter(pk=old_pref.pk).exists()
    assert CustomerSmsPreference.objects.filter(pk=recent_pref.pk).exists()


@pytest.mark.django_db
def test_purge_old_sms_preferences_deletes_only_old_records(organizer):
    old_customer = _create_customer(organizer, "old2@example.com")
    recent_customer = _create_customer(organizer, "recent2@example.com")

    old_pref = CustomerSmsPreference.objects.create(
        customer=old_customer,
        sms_opt_in=False,
    )
    recent_pref = CustomerSmsPreference.objects.create(
        customer=recent_customer,
        sms_opt_in=True,
    )

    now = timezone.now()
    CustomerSmsPreference.objects.filter(pk=old_pref.pk).update(
        last_changed=now - timedelta(days=900)
    )
    CustomerSmsPreference.objects.filter(pk=recent_pref.pk).update(
        last_changed=now - timedelta(days=100)
    )

    out = StringIO()
    call_command("purge_old_sms_preferences", stdout=out)

    assert "Deleted" in out.getvalue()
    assert not CustomerSmsPreference.objects.filter(pk=old_pref.pk).exists()
    assert CustomerSmsPreference.objects.filter(pk=recent_pref.pk).exists()
