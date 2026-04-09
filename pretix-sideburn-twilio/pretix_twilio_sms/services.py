"""
Twilio SMS plugin services: waiting list voucher SMS (queued after email).
"""
import logging
import re
from urllib.parse import urlencode

from django_scopes import scope, scopes_disabled

from pretix.base.services.tasks import TransactionAwareTask
from pretix.celery_app import app
from pretix.multidomain.urlreverse import build_absolute_uri

from pretix_twilio_sms.models import CustomerSmsPreference

logger = logging.getLogger(__name__)

# Common footer for SMS opt-out compliance.
SMS_OPT_OUT_FOOTER = "Reply STOP to opt out."

# Message sent when we cannot resolve a waiting-list voucher URL.
WAITING_LIST_SMS_MESSAGE = (
    f"Your Sideburn waitlist number is up! {SMS_OPT_OUT_FOOTER}"
)

# Minimum number of digits for a plausible phone number (E.164 allows 10–15).
MIN_PHONE_DIGITS = 10


def _build_waiting_list_redeem_url(event, voucher):
    """
    Build the absolute voucher redemption URL for waiting-list SMS messages.
    """
    if not event or not voucher:
        return None
    url_params = {"voucher": voucher.code}
    if voucher.subevent_id:
        url_params["subevent"] = voucher.subevent_id
    return build_absolute_uri(event, "presale:event.redeem") + "?" + urlencode(url_params)


def _build_waiting_list_sms_message(event, voucher):
    """
    Build waiting-list SMS text with direct redeem link + opt-out footer.
    """
    redeem_url = _build_waiting_list_redeem_url(event, voucher)
    if not redeem_url:
        return WAITING_LIST_SMS_MESSAGE
    return (
        f"Your Sideburn waitlist number is up! Use your voucher now: {redeem_url} "
        f"{SMS_OPT_OUT_FOOTER}"
    )


def _get_twilio_config():
    """
    Load Twilio credentials from global settings.

    Returns dict with keys: account_sid, auth_token, from_number.
    Returns None if any required value is missing.
    """
    from pretix.base.settings import GlobalSettingsObject

    gs = GlobalSettingsObject()
    account_sid = (gs.settings.twilio_account_sid or "").strip()
    auth_token = gs.settings.twilio_auth_token
    from_number = (gs.settings.twilio_phone_number or "").strip()
    if not account_sid or not auth_token or not from_number:
        return None
    return {
        "account_sid": account_sid,
        "auth_token": auth_token,
        "from_number": from_number,
    }


def _is_valid_phone(phone):
    """
    Validate that a value looks like a usable phone number for SMS.

    Accepts str or objects that stringify to a number (e.g. PhoneNumber).
    Requires non-empty, stripped, and at least MIN_PHONE_DIGITS digits.
    """
    if phone is None:
        return False
    cleaned = (phone.strip() if isinstance(phone, str) else str(phone)).strip()
    if not cleaned:
        return False
    digits = re.sub(r"\D", "", cleaned)
    return len(digits) >= MIN_PHONE_DIGITS


def send_sms_to_customer(
    *,
    phone,
    sms_opt_in,
    message=None,
    customer_id=None,
    event_id=None,
    entry_id=None,
):
    """
    Send an SMS to a customer using the Twilio SDK.

    Only sends if sms_opt_in is True and phone passes validation.
    Uses global Twilio settings (account SID, auth token, from number).
    Logs Twilio errors and does not raise, so callers (e.g. email flow) are not broken.
    """
    if not sms_opt_in:
        logger.info(
            "pretix_twilio_sms: send_sms_to_customer skip: sms_opt_in is False "
            "(customer_id=%s event_id=%s entry_id=%s)",
            customer_id,
            event_id,
            entry_id,
        )
        return

    if not _is_valid_phone(phone):
        logger.info(
            "pretix_twilio_sms: send_sms_to_customer skip: invalid or missing phone "
            "(customer_id=%s event_id=%s entry_id=%s, phone=%s)",
            customer_id,
            event_id,
            entry_id,
            phone,
        )
        return

    config = _get_twilio_config()
    if not config:
        logger.warning(
            "pretix_twilio_sms: send_sms_to_customer skip: Twilio not configured "
            "(missing account_sid, auth_token, or twilio_phone_number)"
        )
        return

    body = (message or WAITING_LIST_SMS_MESSAGE).strip()
    if not body:
        logger.warning("pretix_twilio_sms: send_sms_to_customer skip: empty message")
        return

    try:
        from twilio.rest import Client

        client = Client(config["account_sid"], config["auth_token"])
        cleaned_phone = phone.strip() if isinstance(phone, str) else str(phone)
        client.messages.create(
            body=body,
            from_=config["from_number"],
            to=cleaned_phone,
        )
        logger.info(
            "pretix_twilio_sms: send_sms_to_customer sent (customer_id=%s event_id=%s entry_id=%s)",
            customer_id,
            event_id,
            entry_id,
        )
    except Exception as e:
        logger.exception(
            "pretix_twilio_sms: send_sms_to_customer Twilio error (customer_id=%s event_id=%s entry_id=%s): %s",
            customer_id,
            event_id,
            entry_id,
            e,
        )


def _get_customer_and_phone(waiting_list_entry):
    """
    Resolve customer by organizer + email and determine phone number.

    Returns (customer or None, phone_str or None, sms_opt_in bool).
    """
    from pretix.base.models import Customer

    organizer = waiting_list_entry.event.organizer
    email = (waiting_list_entry.email or "").strip().lower()
    if not email:
        return None, None, False

    with scope(organizer=organizer):
        try:
            customer = Customer.objects.get(organizer=organizer, email=email)
        except Customer.DoesNotExist:
            customer = None

    phone = None
    if customer and getattr(customer, "phone", None):
        phone = str(customer.phone) if customer.phone else None
    if not phone and getattr(waiting_list_entry, "phone", None):
        phone = str(waiting_list_entry.phone) if waiting_list_entry.phone else None

    sms_opt_in = False
    if customer:
        try:
            pref = customer.sms_preference
            sms_opt_in = pref.sms_opt_in
        except CustomerSmsPreference.DoesNotExist:
            pass

    return customer, phone, sms_opt_in


def send_waiting_list_sms_dummy(
    *,
    event_id,
    entry_id,
    customer_id=None,
    phone=None,
    sms_opt_in=False,
    message=None,
):
    """
    Dummy handler: run a no-op "command" with all variables needed for SMS.

    Accepts serializable IDs so the Celery task can call it without DB lookups.
    Replace this with real Twilio send when ready.
    """
    logger.info(
        "pretix_twilio_sms: would send waiting list SMS (dummy). "
        "event_id=%s entry_id=%s customer_id=%s phone=%s sms_opt_in=%s message=%s",
        event_id,
        entry_id,
        customer_id,
        phone,
        sms_opt_in,
        message or WAITING_LIST_SMS_MESSAGE,
    )


# Pluggable sender: task calls this so tests can patch to send_waiting_list_sms_dummy.
_sms_sender = send_sms_to_customer


def queue_waiting_list_sms_after_mail(*, event_id, order, customer, to):
    """
    If this mail run was a waiting list voucher email, find the entry and
    queue the SMS Celery task (runs after email has been sent).
    """
    logger.info(
        "pretix_twilio_sms: queue_waiting_list_sms_after_mail called "
        "event_id=%s order=%s customer=%s to=%s",
        event_id,
        order,
        customer,
        to,
    )
    if not event_id or order is not None or customer is not None:
        logger.info(
            "pretix_twilio_sms: queue_waiting_list_sms_after_mail skip: "
            "not waiting-list mail (need event, no order, no customer)"
        )
        return
    if not to or not isinstance(to, (list, tuple)) or len(to) < 1:
        logger.info(
            "pretix_twilio_sms: queue_waiting_list_sms_after_mail skip: no to"
        )
        return

    recipient = (to[0] or "").strip()
    if not recipient or "@" not in recipient:
        logger.info(
            "pretix_twilio_sms: queue_waiting_list_sms_after_mail skip: "
            "no valid recipient"
        )
        return

    from pretix.base.models import Event
    from pretix.base.models.waitinglist import WaitingListEntry

    with scopes_disabled():
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            logger.info(
                "pretix_twilio_sms: queue_waiting_list_sms_after_mail skip: "
                "event_id=%s not found",
                event_id,
            )
            return

    with scope(organizer=event.organizer):
        entry = (
            WaitingListEntry.objects.filter(
                event_id=event_id,
                email__iexact=recipient,
                voucher__isnull=False,
            )
            .order_by("-pk")
            .first()
        )
    if not entry:
        logger.info(
            "pretix_twilio_sms: queue_waiting_list_sms_after_mail skip: "
            "no waiting list entry with voucher for event_id=%s recipient=%s",
            event_id,
            recipient,
        )
        return

    customer, phone, sms_opt_in = _get_customer_and_phone(entry)

    logger.info(
        "pretix_twilio_sms: queueing waiting list SMS task entry_id=%s event_id=%s",
        entry.pk,
        event_id,
    )
    send_waiting_list_sms_task.apply_async(
        kwargs={
            "event_id": event.pk,
            "entry_id": entry.pk,
            "customer_id": customer.pk if customer else None,
            "phone": phone,
            "sms_opt_in": sms_opt_in,
            "message": _build_waiting_list_sms_message(event, entry.voucher),
        }
    )


@app.task(base=TransactionAwareTask, bind=True, acks_late=True)
def send_waiting_list_sms_task(
    self,
    event_id,
    entry_id,
    customer_id=None,
    phone=None,
    sms_opt_in=False,
    message=None,
):
    """
    Celery task: run waiting list SMS with pre-resolved data.
    Queued only after the voucher email has been sent; receives data from
    queue_waiting_list_sms_after_mail so no DB lookups are needed.
    Uses _sms_sender (send_sms_to_customer by default; tests can patch to
    send_waiting_list_sms_dummy to avoid hitting Twilio).
    """
    logger.info(
        "pretix_twilio_sms: send_waiting_list_sms_task started entry_id=%s",
        entry_id,
    )
    _sms_sender(
        phone=phone,
        sms_opt_in=sms_opt_in,
        message=message or WAITING_LIST_SMS_MESSAGE,
        customer_id=customer_id,
        event_id=event_id,
        entry_id=entry_id,
    )
