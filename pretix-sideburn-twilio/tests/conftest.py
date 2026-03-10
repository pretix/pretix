# put your pytest fixtures here

import pytest

from pretix_twilio_sms import services as twilio_services


@pytest.fixture(autouse=True)
def use_dummy_sms_sender():
    """Use dummy SMS sender in tests so we don't hit Twilio."""
    print("Using dummy SMS sender in tests")
    original = twilio_services._sms_sender
    twilio_services._sms_sender = twilio_services.send_waiting_list_sms_dummy
    try:
        yield
    finally:
        twilio_services._sms_sender = original
        print("Restored original SMS sender in tests")
