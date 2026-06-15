import logging
from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _

from pretix.base.forms import SecretKeySettingsField
from pretix.base.signals import register_global_settings, waiting_list_voucher_sent
from pretix.presale.signals import (
    change_information_form_class, customer_profile_extra, waitinglist_form_class,
)

from .services import queue_waiting_list_sms_for_entry

logger = logging.getLogger(__name__)


@receiver(register_global_settings, dispatch_uid="twilio_sms_global_settings")
def register_twilio_global_settings(sender, **kwargs):
    """
    Register global configuration settings for the Twilio SMS plugin.

    These values are configured once per pretix installation and are used by
    the plugin to authenticate with Twilio and validate incoming webhooks.
    """
    return OrderedDict(
        [
            (
                "twilio_account_sid",
                forms.CharField(
                    label=_("Twilio Account SID"),
                    required=False,
                    help_text=_(
                        "The Account SID of your Twilio project, used to authenticate API requests."
                    ),
                ),
            ),
            (
                "twilio_auth_token",
                SecretKeySettingsField(
                    label=_("Twilio Auth Token"),
                    required=False,
                    help_text=_(
                        "The Auth Token of your Twilio project. This will be stored encrypted."
                    ),
                ),
            ),
            (
                "twilio_phone_number",
                forms.CharField(
                    label=_("Twilio phone number"),
                    required=False,
                    help_text=_(
                        "The Twilio phone number that will be used as the sender for SMS messages."
                    ),
                ),
            ),
            (
                "twilio_webhook_auth_token",
                SecretKeySettingsField(
                    label=_("Twilio webhook auth token"),
                    required=False,
                    help_text=_(
                        "Optional shared secret used to validate incoming Twilio webhooks."
                    ),
                ),
            ),
        ]
    )


@receiver(waitinglist_form_class, dispatch_uid="twilio_sms_waitinglist_form")
def inject_waitinglist_form_with_sms(sender, **kwargs):
    """
    Provide an extended waiting list form that adds SMS opt-in and phone
    handling for CustomerSmsPreference and customer.phone updates.
    """
    from .forms import WaitingListFormWithSms

    return WaitingListFormWithSms


@receiver(change_information_form_class, dispatch_uid="twilio_sms_change_info_form")
def inject_change_info_form_with_sms(sender, **kwargs):
    from .forms import ChangeInfoFormWithSms

    return ChangeInfoFormWithSms


@receiver(customer_profile_extra, dispatch_uid="twilio_sms_customer_profile_extra")
def render_customer_sms_status(sender, customer, **kwargs):
    template = get_template("pretix_twilio_sms/fragment/customer_sms_status.html")
    return template.render({"customer": customer, "request": sender}, request=sender)


@receiver(waiting_list_voucher_sent, dispatch_uid="twilio_sms_waiting_list_voucher_sent")
def queue_sms_on_voucher_sent(sender, entry, **kwargs):
    logger.info(
        "pretix_twilio_sms: waiting list voucher handled, checking for SMS "
        "event_id=%s entry_id=%s",
        getattr(getattr(entry, "event", None), "id", None),
        getattr(entry, "pk", None),
    )
    try:
        queue_waiting_list_sms_for_entry(entry=entry)
    except Exception:
        logger.exception(
            "pretix_twilio_sms: failed queuing waiting list SMS "
            "event_id=%s entry_id=%s",
            getattr(getattr(entry, "event", None), "id", None),
            getattr(entry, "pk", None),
        )
