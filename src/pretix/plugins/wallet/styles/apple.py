from .base import (
    FieldEntry,
    FieldEntryContentType,
    FieldContentType,
    ImageFieldGroup,
    PlaceholderFieldGroup,
    TextFieldGroup,
    WalletPlatform,
    PassStyle,
)
from django.utils.translation import gettext as _
from i18nfield.strings import LazyI18nString


class ApplePlatform(WalletPlatform):
    identifier = "apple"
    name = _("Apple")


class AppleWalletStyle(PassStyle):
    platform = ApplePlatform

class AppleWalletEventTicket(AppleWalletStyle):
    identifier = "event_1"
    name = _("Event Ticket Layout 1")
    fieldgroups = [
        ImageFieldGroup(
            identifier="logo",
            name=_("Logo"),
            min_entries=1,
            max_entries=1,
            labels=False,
            default_entries=[
                FieldEntry(
                    type=FieldEntryContentType.IMAGE,
                    label=LazyI18nString("logo"),
                    content="event:image",
                )
            ],
        ),
        TextFieldGroup(
            identifier="primary",
            name=_("Primary"),
            min_entries=1,
            max_entries=1,
            default_entries=[
                FieldEntry(
                    type=FieldEntryContentType.PLACEHOLDER,
                    label=LazyI18nString({"de": "Tickettyp", "en": "Ticket type"}),
                    content="item",
                )
            ],  # TODO: support Lazyi18nproxy here
            description=_("These fields appear prominently featured on the pass.")
        ),
        TextFieldGroup(
            identifier="secondary", name=_("Secondary"), max_entries=4
        ),  # TODO: validation of max field count if combined "Coupons, store cards, and generic passes with a square barcode can have a total of up to four secondary and auxiliary fields, combined."
        TextFieldGroup(
            identifier="headers", name=_("Header"), max_entries=3
        ),  # TODO: header image
        TextFieldGroup(identifier="auxillary", name=_("Auxillary"), max_entries=4),
        TextFieldGroup(identifier="back", name=_("Back")),
    ]
    # preview_image = "apple/event_ticket.svg"


