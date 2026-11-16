
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.dispatch import receiver

from pretix.base.ticketoutput import BaseTicketOutput
from pretix.base.signals import register_ticket_outputs


class WalletSettingsHolder(BaseTicketOutput):
    """
    Meta ticket output provider for control settings
    TODO(wallet): replace with custom view?
    """
    identifier = "wallet"
    verbose_name = _("Wallet")

    is_meta = True
    is_enabled = False
    preview_allowed = False

    def settings_content_render(self, request) -> str:
        return render_to_string(
            "pretixcontrol/wallet/settings_content.html", {"request": request}
        )


@receiver(register_ticket_outputs, dispatch_uid="ticketoutput_wallet")
def register_output(sender, **kwargs):
    return WalletSettingsHolder
