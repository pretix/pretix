from typing import Any

from pretix.plugins.wallet.styles.base import (
    FieldGroup,
    FieldGroupDisplay,
    FloatSettingsField,
    TextFieldGroup,
    WalletPlatform,
    PassStyle,
    PlaceholderFieldEntry,
    SettingsField,
)
from django.utils.translation import gettext as _, override
from i18nfield.strings import LazyI18nString
import io
import hashlib
import zipfile
import cryptography
import cryptography.x509
import cryptography.hazmat.primitives.serialization.pkcs7
import cryptography.hazmat.primitives.hashes
import json
from django.contrib.staticfiles import finders
from pretix.base.models import OrderPosition
from django.utils.encoding import force_bytes
import tempfile
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
import logging
from django.forms import ValidationError

logger = logging.getLogger()


class ApplePlatform(WalletPlatform):
    identifier = "apple"
    name = _("Apple")


class FormattedLazyI18nString:
    def __init__(self, base_str: LazyI18nString, **format_args: str):
        self.base_str = base_str
        self.format_args = format_args

    def localize(self, language):
        return self.base_str.localize(language).format(**self.format_args)


def lazyi18nstring_from_gettext(text: str, locales: set[str]) -> LazyI18nString:
    data = {}
    for locale in locales:
        with override(locale):
            data[locale] = _(text)
    return LazyI18nString(data)


class StringResource:
    entries: dict[str, LazyI18nString | FormattedLazyI18nString]
    locales: set[str]

    def __init__(self, locales):
        self.entries = {}
        self.locales = set(locales)

    def add_entry(self, key: str, value: LazyI18nString | FormattedLazyI18nString):
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
            output += (
                f'"{self.escape(key)}" = "{self.escape(entry.localize(language))}";\n'
            )
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


def convert_to_png(file, max_size=None):
    # TODO: move validation to upload
    try:
        from PIL import Image
    except ImportError:
        return file

    file.open("rb")
    file.seek(0)
    try:
        with (
            Image.open(file, formats=settings.PILLOW_FORMATS_IMAGE) as im,
            tempfile.NamedTemporaryFile("rb", suffix=".png") as tmpfile,
        ):
            if max_size:
                im.thumbnail(max_size)
            im.save(tmpfile.name)
            tmpfile.seek(0)
            return SimpleUploadedFile("picture.png", tmpfile.read(), "image png")
    except IOError:
        logger.exception("Could not convert image to PNG.")
        raise ValidationError(
            _("The file you uploaded could not be converted to PNG format.")
        )


class AppleWalletStyle(PassStyle):
    @property
    def settings(self):
        return [
            SettingsField(
                identifier="logo",
                label=_("Logo"),
                type="image",
                required=False,
                help_text="Will be displayed on the top left corner of the pass",
            ),
            SettingsField(
                identifier="icon",
                label=_("Icon"),
                type="image",
                required=False,
                help_text="Will be displayed as the file icon",
            ),
            SettingsField(
                identifier="background",
                label=_("Background"),
                type="image",
                required=False,
            ),
            FloatSettingsField(
                identifier="lat", label=_("Latitude"), required=False, min=-90, max=90
            ),
            FloatSettingsField(
                identifier="long",
                label=_("Longitude"),
                required=False,
                min=-180,
                max=180,
            ),
            SettingsField(
                identifier="bg_color",
                label=_("Background Color"),
                type="color",
                required=False,
            ),
            SettingsField(
                identifier="fg_color",
                label=_("Foreground Color"),
                type="color",
                required=False,
            ),
            SettingsField(
                identifier="label_color",
                label=_("Label Color"),
                type="color",
                required=False,
            ),
        ]

    def pass_content(self, fields, strings):
        raise NotImplementedError()

    def generate_pass_json(self, fields, op, strings):
        event = op.subevent or op.order.event
        tz = event.timezone

        ticket = str(op.item.name)
        if op.variation:
            ticket += " - " + str(op.variation)

        description = FormattedLazyI18nString(
            LazyI18nString.from_gettext("Ticket for {event} ({product})"),
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

        if "bg_color" in self.layout["settings"]:
            pass_json["backgroundColor"] = self.layout["settings"][
                "bg_color"
            ]  # TODO: specified as a CSS-style RGB triple, such as rgb(100, 10, 110).
        if "fg_color" in self.layout["settings"]:
            pass_json["foregroundColor"] = self.layout["settings"][
                "fg_color"
            ]  # TODO: specified as a CSS-style RGB triple, such as rgb(100, 10, 110).
        if "label_color" in self.layout["settings"]:
            pass_json["labelColor"] = self.layout["settings"][
                "label_color"
            ]  # TODO: specified as a CSS-style RGB triple, such as rgb(100, 10, 110).

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
            if "lat" in self.layout["settings"] and "long" in self.layout["settings"]:
                pass_json["locations"] = {
                    "latitude": float(self.layout["settings"]["lat"]),
                    "longitude": float(self.layout["settings"]["long"]),
                }
            elif event.geo_lat and event.geo_lon:
                pass_json["locations"] = {
                    "latitude": float(event.get_lat),
                    "longitude": float(event.get_lon),
                }

        print(pass_json)
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

        if file := self.file_settings.get("logo"):
            logo = convert_to_png(
                file, (480, 150)
            )  # TODO: check max_size against apple HIG
        else:
            logo = open(finders.find("pretixplugins/wallet/logo.png"), "rb")

        if file := self.file_settings.get("icon"):
            icon = convert_to_png(
                file, max_size=(87, 87)
            )  # TODO: check max_size against apple HIG
        else:
            icon = open(finders.find("pretixplugins/wallet/icon.png"), "rb")

        pkpass.add_file("icon.png", icon.read())
        pkpass.add_file("logo.png", logo.read())

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
            ),
            TextFieldGroup(
                identifier="header",
                name=_("Header"),
                max_entries=3,
                context_args={"order_position"},
                default_entries=[
                    PlaceholderFieldEntry(
                        content="admission_or_date_from",
                        label=lazyi18nstring_from_gettext(
                            "Admission", self.event.settings.locales
                        ),
                    ),
                ],
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
            ),
            TextFieldGroup(
                identifier="secondary",
                name=_("Secondary"),
                max_entries=4,
                context_args={"order_position"},
                default_entries=[
                    PlaceholderFieldEntry(
                        content="item_with_variation",
                        label=lazyi18nstring_from_gettext(
                            "Product", self.event.settings.locales
                        ),
                    )
                ],
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
                        label=lazyi18nstring_from_gettext(
                            "Seat", locales=self.event.settings.locales
                        ),
                    ),
                    PlaceholderFieldEntry(
                        content="attendee_name",
                    ),
                    PlaceholderFieldEntry(
                        content="program_start",
                        label=lazyi18nstring_from_gettext(
                            "From", locales=self.event.settings.locales
                        ),
                    ),
                    PlaceholderFieldEntry(
                        content="program_end",
                        label=lazyi18nstring_from_gettext(
                            "To", locales=self.event.settings.locales
                        ),
                    ),
                ],
            ),
            TextFieldGroup(
                identifier="code",
                name=_("QR-Code"),
                max_entries=1,
                display=FieldGroupDisplay.CODE,
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
                        label=lazyi18nstring_from_gettext(
                            "Ordered by", self.event.settings.locales
                        ),
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
    def preview_layout(self):
        return [
            [
                {
                    "children": [
                        {"setting": "logo"},
                        {
                            "fieldgroup": "logo_text",
                            "relSize": 3,
                            "display": ["bold", "large", "centered"],
                        },
                        {
                            "fieldgroup": "header",
                            "relSize": 2,
                            "display": ["large", "tight"],
                        },
                    ]
                },
                {"fieldgroup": "primary", "display": "large"},
                {"fieldgroup": "secondary"},
                {"fieldgroup": "auxiliary"},
                {"fieldgroup": "code"},
            ],
            [{"fieldgroup": "back", "direction": "column"}],
        ]

    def convert_fields(self, strings, fields, prefix):
        converted = []
        for i, f in enumerate(fields):
            converted_field = {**f, "key": f"{prefix}-{i}"}
            if "label" in converted_field and isinstance(
                converted_field["label"], LazyI18nString
            ):
                strings.add_entry(f"{prefix}-{i}-label", converted_field["label"])
                converted_field["label"] = f"{prefix}-{i}-label"

            if isinstance(converted_field["value"], LazyI18nString):
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
