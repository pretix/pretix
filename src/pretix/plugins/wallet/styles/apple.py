import hashlib
import io
import json
import logging
import zipfile
from typing import Any

import cryptography
import cryptography.hazmat.primitives.hashes
import cryptography.hazmat.primitives.serialization.pkcs7
import cryptography.x509
from django.utils.encoding import force_bytes
from django.utils.translation import gettext as _

from pretix.base.models import OrderPosition
from pretix.plugins.wallet.i18n import (
    FormattingLocalizableString,
    GettextLocalizableString,
    MaybeTranslatedString,
)
from pretix.plugins.wallet.styles.base import (
    FieldGroup,
    FieldGroupDisplay,
    PassStyle,
    PlaceholderFieldEntry,
    TextFieldGroup,
    WalletPlatform,
)
from pretix.plugins.wallet.styles.settings import ImageSettingsField

from .settings import ColorSettingsField, FloatSettingsField, convert_to_png

logger = logging.getLogger()


class ApplePlatform(WalletPlatform):
    identifier = "apple"
    name = _("Apple")


class StringResource:
    entries: dict[str, MaybeTranslatedString]
    locales: set[str]

    def __init__(self, locales):
        self.entries = {}
        self.locales = set(locales)

    def add_entry(self, key: str, value: MaybeTranslatedString):
        if key in self.entries:
            raise ValueError(f"{key} already exists in this StringResource")
        self.entries[key] = value

    def escape(self, string):
        return string.translate(
            str.maketrans({'"': '\\"', "\r": "\\r", "\n": "\\n", "\\": "\\\\"})
        )

    def generate_resource(self, language):
        output = ""
        for key, entry in self.entries.items():
            if isinstance(entry, str):
                output += f'"{self.escape(key)}" = "{self.escape(entry)}";\n'
            else:
                output += f'"{self.escape(key)}" = "{self.escape(entry.localize(language))}";\n'
        return output.strip()

    def generate(self):
        return {language: self.generate_resource(language) for language in self.locales}


class SignedZipFile:
    """Generates a zip-file with manifest and signature as apple expects a pkpass file to be"""

    def __init__(
        self,
        ca_certificate: str | bytes,
        certificate: str | bytes,
        key: str | bytes,
        password,
    ):
        self.ca_certificate = cryptography.x509.load_pem_x509_certificate(
            force_bytes(ca_certificate)
        )
        self.certificate = cryptography.x509.load_pem_x509_certificate(
            force_bytes(certificate)
        )
        self.key = cryptography.hazmat.primitives.serialization.load_pem_private_key(
            force_bytes(key), force_bytes(password) if password else None
        )
        self.password = password

        self.file = io.BytesIO()
        self.zip_file = zipfile.ZipFile(self.file, "w")
        self.manifest = {}

    def sign(self, data: bytes):
        return (
            cryptography.hazmat.primitives.serialization.pkcs7.PKCS7SignatureBuilder()
            .set_data(data)
            .add_signer(
                self.certificate,
                self.key,
                cryptography.hazmat.primitives.hashes.SHA256(),
            )
            .add_certificate(self.ca_certificate)
            .sign(
                cryptography.hazmat.primitives.serialization.Encoding.DER,
                [
                    cryptography.hazmat.primitives.serialization.pkcs7.PKCS7Options.Binary,
                    cryptography.hazmat.primitives.serialization.pkcs7.PKCS7Options.DetachedSignature,
                ],
            )
        )

    def finish(self):
        manifest = json.dumps(self.manifest).encode()
        signature = self.sign(manifest)
        self.add_file("manifest.json", manifest)
        self.add_file("signature", signature)
        self.zip_file.close()
        return self.file.getvalue()

    def add_file(self, filename: str, content: str | bytes):
        if isinstance(content, str):
            content = content.encode()

        with self.zip_file.open(filename, "w") as f:
            f.write(content)
        self.manifest[filename] = hashlib.sha1(content).hexdigest()


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

    def generate_pass_json(self, fields, op, strings):
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

        serialNumber = "%s-%s-%s-%d" % (
            self.event.organizer.slug,
            self.event.slug,
            op.order.code,
            op.pk,
        )

        pass_json = {
            "formatVersion": 1,
            "description": "description",
            "organizationName": self.event.organizer.name,
            "passTypeIdentifier": self.event.settings.wallet_apple_pass_type_id,
            "teamIdentifier": self.event.settings.wallet_apple_team_id,
            "serialNumber": serialNumber,
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

    def generate(self, op: OrderPosition):
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

        pass_json = self.generate_pass_json(fields, op, strings)

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
        result = pkpass.finish()
        return filename, "application/vnd.apple.pkpass", result


class AppleWalletEventTicket(AppleWalletStyle):
    identifier = "event_1"
    name = _("Event Ticket Layout 1")

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
