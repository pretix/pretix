from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from pretix.base.forms import SecretKeySettingsField
from pretix.base.signals import register_global_settings


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
