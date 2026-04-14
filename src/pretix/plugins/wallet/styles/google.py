from .base import PassStyle, PredefinedFieldGroup, TextFieldGroup, WalletPlatform
from django.utils.translation import gettext_lazy as _

class GooglePlatform(WalletPlatform):
    identifier = "google"
    name = _("Google")


class GoogleWalletStyle(PassStyle):
    platform = GooglePlatform


class GoogleWalletEventTicket(PassStyle):
    identifier = "event"
    name = "Event Ticket"
    platform = GooglePlatform
    fieldgroups = [
        PredefinedFieldGroup(identifier="seating", name=_("Seating")),
        TextFieldGroup(identifier="qrcode", name=_("QR-Code"), labels=False),
    ]
