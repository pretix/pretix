import json
import logging
from typing import Any

from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from django.db import transaction

from pretix.base.models import OrderPosition
from pretix.helpers import OF_SELF
from pretix.multidomain.urlreverse import eventreverse_absolute
from pretix.plugins.wallet.i18n import (
    FormattingLocalizableString, GettextLocalizableString,
)
from ...models import AppleWalletPass
from ..base import (
    FieldGroup, FieldGroupDisplay, PassStyle, PlaceholderFieldEntry,
    TextFieldGroup,
)
from ..settings import ImageSettingsField

from ..settings import ColorSettingsField, FloatSettingsField, convert_to_png
from .platform import SignedZipFile, StringResource

logger = logging.getLogger("pretix.plugins.wallet.apple")


class AppleWalletStyle(PassStyle):
    @property
    def settings(self):
        return [
            ImageSettingsField(
                identifier="logo",
                label=_("Logo"),
                help_text=_("Will be displayed on the top left corner of the pass"),
                default="pretixplugins/wallet/logo.png",
            ),
            ImageSettingsField(
                identifier="icon",
                label=_("Icon"),
                help_text=_("Will be displayed as the file icon"),
                default="pretixplugins/wallet/icon.png",
            ),
            ImageSettingsField(identifier="background", label=_("Background Image")),
            ColorSettingsField(
                identifier="bg_color",
                label=_("Background Color"),
            ),
            ColorSettingsField(
                identifier="fg_color",
                label=_("Foreground Color"),
                help_text=_(
                    "This color is ignored if a background image is set. Instead, the text will be displayed in white."
                ),
                default=self.event.settings.primary_color,
            ),
            ColorSettingsField(
                identifier="label_color", label=_("Label Color"), default="#000000"
            ),
            FloatSettingsField(
                identifier="lat",
                label=_("Latitude"),
                min=-90,
                max=90,
                default=self.event.geo_lat,
            ),
            FloatSettingsField(
                identifier="long",
                label=_("Longitude"),
                min=-180,
                max=180,
                default=self.event.geo_lon,
            ),
        ]

    def pass_content(self, fields, strings):
        raise NotImplementedError()

    def generate_pass_json(
        self, fields, op, strings, pass_type, team_id, serial_number, auth_token
    ):
        event = op.subevent or op.order.event
        tz = event.timezone

        ticket = (
            FormattingLocalizableString(
                "{name} - {variation}", name=op.item.name, variation=op.variation.value
            )
            if op.variation
            else op.item.name
        )

        description = FormattingLocalizableString(
            GettextLocalizableString.gettext("Ticket for {event} ({product})"),
            event=self.event.name,
            product=ticket,
        )
        strings.add_entry("description", description)

        pass_json = {
            "formatVersion": 1,
            "description": "description",
            "organizationName": self.event.organizer.name,
            "passTypeIdentifier": pass_type,
            "teamIdentifier": team_id,
            "serialNumber": serial_number,
            "webServiceURL": eventreverse_absolute(self.event, "presale:event.index")
            + "_wallet/apple/",
            "authenticationToken": auth_token,
            **self.pass_content(fields, strings),
        }

        # TODO: Apples specs says this should be  "specified as a CSS-style RGB triple, such as rgb(100, 10, 110).", but hex codes work as well
        if bg_color := self.get_cleaned_setting("bg_color"):
            pass_json["backgroundColor"] = bg_color
        if fg_color := self.get_cleaned_setting("fg_color"):
            pass_json["foregroundColor"] = fg_color
        if label_color := self.get_cleaned_setting("label_color"):
            pass_json["labelColor"] = label_color

        if self.get_cleaned_setting("background"):
            # iOS ignores the set foregroundColor if a background is set and uses white instead.
            # Explicitly set white in this case so the pass looks the same on all platforms
            # https://developer.apple.com/forums/thread/809417
            pass_json["foregroundColor"] = "#ffffff"
            # macOS always shows transparency as black, iOS as backgroundColor.
            # Explicitly set black in this case so the pass looks the same on all platforms
            pass_json["backgroundColor"] = "#000000"

        if "expirationDate" not in pass_json:
            if op.valid_until:
                pass_json["expirationDate"] = op.valid_until.astimezone(tz).isoformat()
            elif event.settings.show_date_to and event.date_to:
                pass_json["expirationDate"] = event.date_to.astimezone(tz).isoformat()

        if "relevantDates" not in pass_json:
            if op.valid_from and op.valid_to:
                pass_json["relevantDates"] = [
                    {
                        "startDate": op.valid_from.astimezone(tz).isoformat(),
                        "endDate": op.valid_to.astimezone(tz).isoformat(),
                    }
                ]
            elif op.valid_from:
                pass_json["relevantDates"] = [
                    {"date": op.valid_from.astimezone(tz).isoformat()}
                ]
            elif event.settings.show_date_to and event.date_to:
                pass_json["relevantDates"] = [
                    {
                        "startDate": event.date_from.astimezone(tz).isoformat(),
                        "endDate": event.date_to.astimezone(tz).isoformat(),
                    }
                ]
            else:
                pass_json["relevantDates"] = [
                    {"date": event.date_from.astimezone(tz).isoformat()}
                ]

        # TODO: also fill relevantDates from program times

        if "locations" not in pass_json:
            if (lat := self.get_cleaned_setting("lat")) and (
                long := self.get_cleaned_setting("long")
            ):
                pass_json["locations"] = {
                    "latitude": lat,
                    "longitude": long,
                }

        return pass_json

    @transaction.atomic
    def generate(self, op: OrderPosition):
        pass_type = self.event.settings.wallet_apple_pass_type_id
        team_id = self.event.settings.wallet_apple_team_id
        serial_number = "%s-%s-%s-%d" % (
            self.event.organizer.slug,
            self.event.slug,
            op.order.code,
            op.pk,
        )

        pass_obj, _ = AppleWalletPass.objects.select_for_update(
            of=OF_SELF
        ).get_or_create(
            order_position=op,
            pass_type=pass_type,
            defaults={
                "serial_number": serial_number,
                "pass_type": pass_type,
            },
        )

        order = op.order
        filename = "{}-{}.pkpass".format(order.event.slug, order.code)

        fields = self.get_pass_fields(op)
        pkpass = SignedZipFile(
            self.event.settings.wallet_apple_ca_certificate.read(),
            self.event.settings.wallet_apple_certificate.read(),
            self.event.settings.wallet_apple_key.read(),
            self.event.settings.wallet_apple_key_password,
        )
        strings = StringResource(locales=self.event.settings.locales)

        pass_json = self.generate_pass_json(
            fields, op, strings, pass_type, team_id, pass_obj.serial_number, pass_obj.token
        )

        if file := self.get_cleaned_setting("logo"):
            logo = convert_to_png(
                file, (480, 150)
            )  # TODO: check max_size against apple HIG

        if file := self.get_cleaned_setting("icon"):
            icon = convert_to_png(
                file, max_size=(87, 87)
            )  # TODO: check max_size against apple HIG

        pkpass.add_file("icon.png", icon.read())
        pkpass.add_file("logo.png", logo.read())

        if file := self.get_cleaned_setting("background"):
            background = convert_to_png(
                file, max_size=(540, 660)
            )  # TODO: check max_size against apple HIG
            pkpass.add_file("background.png", background.read())

        for lang, content in strings.generate().items():
            pkpass.add_file(f"{lang}.lproj/pass.strings", content)
        pkpass.add_file("pass.json", json.dumps(pass_json))
        result, manifest = pkpass.finish()

        if pass_obj.content and pass_obj.manifest != manifest:
            pass_obj.content.delete()
            pass_obj.content.save(filename, ContentFile(result, name=filename))
            pass_obj.manifest = manifest
            pass_obj.save()

        return filename, "application/vnd.apple.pkpass", result


class AppleWalletEventTicket(AppleWalletStyle):
    identifier = "event_1"
    name = _("Event Ticket Layout")

    @property
    def fieldgroups(self) -> list[FieldGroup]:
        return [
            TextFieldGroup(
                identifier="logo_text",
                name=_("Logo text"),
                max_entries=1,
                display=FieldGroupDisplay.PLAIN,
                context_args={"order_position"},
                can_overflow=False,
            ),
            TextFieldGroup(
                identifier="header",
                name=_("Header"),
                max_entries=3,
                context_args={"order_position"},
                default_entries=[
                    PlaceholderFieldEntry(
                        content="admission_or_date_from",
                        label=GettextLocalizableString.gettext("Admission"),
                    ),
                ],
                default_overflow="back",
            ),
            TextFieldGroup(
                identifier="primary",
                name=_("Primary"),
                min_entries=1,
                max_entries=1,
                default_entries=[
                    PlaceholderFieldEntry(
                        content="event",
                    )
                ],
                description=_("These fields appear prominently featured on the pass."),
                required=True,
                context_args={"order_position"},
                default_overflow="back",
            ),
            TextFieldGroup(
                identifier="secondary",
                name=_("Secondary"),
                max_entries=4,
                context_args={"order_position"},
                default_entries=[
                    PlaceholderFieldEntry(
                        content="item_with_variation",
                        label=GettextLocalizableString.gettext("Product"),
                    )
                ],
                default_overflow="back",
            ),
            # TODO: validation of max field count if combined "Coupons, store cards, and generic passes
            # with a square barcode can have a total of up to four secondary and auxiliary fields, combined."
            TextFieldGroup(
                identifier="auxiliary",
                name=_("Auxiliary"),
                max_entries=4,
                context_args={"order_position"},
                default_entries=[
                    PlaceholderFieldEntry(
                        content="seat",
                        label=GettextLocalizableString.gettext("Seat"),
                    ),
                    PlaceholderFieldEntry(
                        content="attendee_name",
                    ),
                    PlaceholderFieldEntry(
                        content="program_start",
                        label=GettextLocalizableString.gettext("From"),
                    ),
                    PlaceholderFieldEntry(
                        content="program_end",
                        label=GettextLocalizableString.gettext("To"),
                    ),
                ],
                default_overflow="back",
            ),
            TextFieldGroup(
                identifier="code",
                name=_("QR-Code"),
                max_entries=1,
                display=FieldGroupDisplay.PLAIN,
                default_entries=[
                    PlaceholderFieldEntry(
                        content="secret",
                    )
                ],
                context_args={"order_position"},
            ),
            TextFieldGroup(
                identifier="back",
                name=_("Back"),
                context_args={"order_position"},
                default_entries=[
                    PlaceholderFieldEntry(
                        content="admission",
                    ),
                    PlaceholderFieldEntry(
                        content="attendee_name",
                    ),
                    PlaceholderFieldEntry(
                        content="order_email",
                        label=GettextLocalizableString.gettext("Ordered by"),
                    ),
                    PlaceholderFieldEntry(
                        content="organizer",
                    ),
                    PlaceholderFieldEntry(
                        content="organizer_contact",
                    ),
                    PlaceholderFieldEntry(
                        content="order_code",
                    ),
                    PlaceholderFieldEntry(
                        content="purchase_date",
                    ),
                    PlaceholderFieldEntry(
                        content="website",
                    ),
                ],
            ),
        ]

    @property
    def preview_renderer(self) -> str | None:
        return "apple_eventticket"

    def convert_fields(self, strings, fields, prefix):
        # TODO: detect if a string-value/string-label is the same as a generated field name
        # eg if a placeholder returns "primary-0-label", this would not be shown to the user but instead replaces with the label
        converted = []
        for i, f in enumerate(fields):
            converted_field = {**f, "key": f"{prefix}-{i}"}
            if "label" in converted_field:
                strings.add_entry(f"{prefix}-{i}-label", converted_field["label"])
                converted_field["label"] = f"{prefix}-{i}-label"

            strings.add_entry(f"{prefix}-{i}-value", converted_field["value"])
            converted_field["value"] = f"{prefix}-{i}-value"
            converted.append(converted_field)
        return converted

    def pass_content(self, fields, strings):
        content: dict[str, Any] = {
            "eventTicket": {
                "primaryFields": self.convert_fields(
                    strings, fields["primary"], "primary"
                ),
                "secondaryFields": self.convert_fields(
                    strings, fields["secondary"], "secondary"
                ),
                "auxiliaryFields": self.convert_fields(
                    strings, fields["auxiliary"], "auxiliary"
                ),
                "backFields": self.convert_fields(strings, fields["back"], "back"),
                "headerFields": self.convert_fields(
                    strings, fields["header"], "header"
                ),
            },
        }
        if fields["logo_text"]:
            content["logoText"] = self.convert_fields(
                strings, fields["logo_text"], "logo_text"
            )[0]["value"]

        if fields["code"]:
            content["barcodes"] = [
                {
                    "format": "PKBarcodeFormatQR",
                    "message": str(fields["code"][0]["value"]),
                    "messageEncoding": "utf-8",
                    "altText": str(fields["code"][0]["value"]),
                }
            ]
        return content
