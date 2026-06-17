from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import gettext_lazy, gettext_noop

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import WaitingListEntry
from pretix.base.services.mail import mail

DEFAULT_MAIL_TEXT_WAITING_LIST_CONFIRM = gettext_noop("""Hello,

This is to confirm that you have been added to the lottery for {event}.

Once the ticket lottery has taken place, those selected will receive an email with a voucher to purchase a ticket.

If you are not selected in the initial lottery, you will be added to a waiting list
and will receive an email when a ticket is available for you.

Want to stay in the loop about the latest news about SideBurn? Subscribe to our newsletter here: http://eepurl.com/ij4Off

Best regards,
Your {event} ticketing team""")

DEFAULT_SIGNUP_SUBJECT = gettext_lazy(
    "You have been added to the lottery waiting list for {event}"
)

DUPLICATE_VOUCHER_MESSAGE = gettext_lazy(
    "You have already been assigned a ticket! "
    "Contact ticketing@sideburn.ca if this is in error."
)


def send_signup_confirmation(entry, user=None, auth=None):
    """Send the lottery waiting-list signup confirmation email."""
    with language(entry.locale, entry.event.settings.region):
        template = entry.event.settings.get("mail_text_waiting_list_confirm")
        if not template:
            template = gettext_lazy(DEFAULT_MAIL_TEXT_WAITING_LIST_CONFIRM)
        mail(
            entry.email,
            str(DEFAULT_SIGNUP_SUBJECT).format(event=str(entry.event)),
            template,
            get_email_context(event=entry.event, waiting_list_entry=entry),
            entry.event,
            locale=entry.locale,
        )


def validate_no_active_voucher_duplicate(entry):
    """
    Reject signup when the same email/product already has a live voucher assignment.
    """
    if WaitingListEntry.objects.filter(
        item=entry.item,
        variation=entry.variation,
        email__iexact=entry.email,
        voucher__isnull=False,
        subevent=entry.subevent,
    ).exclude(pk=entry.pk).filter(
        Q(voucher__redeemed__gt=0)
        | Q(voucher__valid_until__isnull=True)
        | Q(voucher__valid_until__gte=now())
    ).exists():
        raise ValidationError(DUPLICATE_VOUCHER_MESSAGE)
