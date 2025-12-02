from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import Organizer, Event
from pretix.helpers.payment import generate_payment_qr_codes


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Verein für Testzwecke e.V.', slug='testverein')
    event = Event.objects.create(
        organizer=o, name='Testveranstaltung', slug='testveranst',
        date_from=now() + timedelta(days=10),
        live=True, is_public=False, currency='EUR',
    )
    event.settings.invoice_address_from = 'Verein für Testzwecke e.V.'
    event.settings.invoice_address_from_zipcode = '1234'
    event.settings.invoice_address_from_city = 'Testhausen'
    event.settings.invoice_address_from_country = 'CH'

    return o, event


@pytest.mark.django_db
def test_payment_qr_codes_euro(env):
    o, event = env
    codes = generate_payment_qr_codes(
        event=event,
        code='TESTVERANST-12345',
        amount=Decimal('123.00'),
        bank_details_sepa_bic='BYLADEM1MIL',
        bank_details_sepa_iban='DE37796500000069799047',
        bank_details_sepa_name='Verein für Testzwecke e.V.',
    )
    assert len(codes) == 2
    assert codes[0]['label'] == 'EPC-QR'
    assert codes[0]['qr_data'] == '''BCD
002
2
SCT
BYLADEM1MIL
Verein fur Testzwecke e.V.
DE37796500000069799047
EUR123.00


TESTVERANST-12345

'''

    assert codes[1]['label'] == 'BezahlCode'
    assert codes[1]['qr_data'] == 'bank://singlepaymentsepa?name=Verein%20f%C3%BCr%20Testzwecke%20e.V.&iban=DE37796500000069799047&bic=BYLADEM1MIL&amount=123%2C00&reason=TESTVERANST-12345&currency=EUR'


@pytest.mark.django_db
def test_payment_qr_codes_swiss(env):
    o, event = env
    codes = generate_payment_qr_codes(
        event=event,
        code='TESTVERANST-12345',
        amount=Decimal('123.00'),
        bank_details_sepa_bic='TESTCHXXXXX',
        bank_details_sepa_iban='CH6389144757654882127',
        bank_details_sepa_name='Verein für Testzwecke e.V.',
    )
    assert codes[0]['label'] == 'QR-bill'
    assert codes[0]['qr_data'] == "\r\n".join([
        "SPC",
        "0200",
        "1",
        "CH6389144757654882127",
        "K",
        "Verein fur Testzwecke e.V.",
        "Verein fur Testzwecke e.V.",
        "1234 Testhausen",
        "",
        "",
        "CH",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "123.00",
        "EUR",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "NON",
        "",
        "TESTVERANST-12345",
        "EPD",
    ])