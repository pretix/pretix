"""
Twilio SMS plugin services: waiting list voucher SMS (queued after email).
"""
import logging

from django_scopes import scope, scopes_disabled

from pretix.base.services.tasks import TransactionAwareTask
from pretix.celery_app import app

from pretix_twilio_sms.models import CustomerSmsPreference

logger = logging.getLogger(__name__)

# Message sent when a waiting list voucher email has been sent (and SMS opt-in is true).
WAITING_LIST_SMS_MESSAGE = (
    "Your Sideburn waitlist number is up! Please check your email for details."
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
            "message": WAITING_LIST_SMS_MESSAGE,
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
    Celery task: run waiting list SMS (dummy or real) with pre-resolved data.
    Queued only after the voucher email has been sent; receives data from
    queue_waiting_list_sms_after_mail so no DB lookups are needed.
    """
    logger.info(
        "pretix_twilio_sms: send_waiting_list_sms_task started entry_id=%s",
        entry_id,
    )
    send_waiting_list_sms_dummy(
        event_id=event_id,
        entry_id=entry_id,
        customer_id=customer_id,
        phone=phone,
        sms_opt_in=sms_opt_in,
        message=message or WAITING_LIST_SMS_MESSAGE,
    )
