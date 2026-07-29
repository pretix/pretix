from typing import Any

from .base import (
    FieldEntryType,
    FieldGroupDisplay,
    ImageFieldGroup,
    PlaceholderFieldGroup,
    PredefinedFieldGroup,
    TextFieldGroup,
    WalletPlatform,
    PassStyle,
    PlaceholderFieldEntry,
)
from django.utils.translation import gettext as _
from i18nfield.strings import LazyI18nString
import io
import hashlib
import zipfile
import cryptography
import cryptography.x509
import cryptography.hazmat.primitives.serialization.pkcs7
import json
from django.contrib.staticfiles import finders
from pretix.base.models import OrderPosition
from django.utils.encoding import force_bytes


class ApplePlatform(WalletPlatform):
    identifier = "apple"
    name = _("Apple")


class StringResource:
    # mapping string in default event locale -> LazyI18nString
    entries: dict[str, LazyI18nString]
    locales: set[str]

    def __init__(self, locales):
        self.entries = {}
        self.locales = set(locales)

    def add_entry(self, key: str, value: LazyI18nString):
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


class AppleWalletStyle(PassStyle):
    def pass_content(self, fields, strings):
        raise NotImplementedError()

    def generate_pass_json(self, fields, context, strings):
        def add_from_context(key):
            value = context.get(key)
            if not value:
                raise ValueError(f"{key} must be set to a truthy value")
            return value

        pass_json = {
            "formatVersion": 1,
            "description": add_from_context("description"),
            "organizationName": add_from_context("organizationName"),
            "passTypeIdentifier": add_from_context("passTypeIdentifier"),
            "teamIdentifier": add_from_context("teamIdentifier"),
            "serialNumber": add_from_context("serialNumber"),
            **self.pass_content(fields, strings),
        }
        return pass_json

    def generate(self, op: OrderPosition):
        context = self.get_context(op)

        order = op.order
        event = order.event
        filename = "{}-{}.pkpass".format(order.event.slug, order.code)

        ticket = str(op.item.name)
        if op.variation:
            ticket += " - " + str(op.variation)

        serialNumber = "%s-%s-%s-%d" % (
            order.event.organizer.slug,
            order.event.slug,
            order.code,
            op.pk,
        )

        context.update({
            "ca_certificate": order.event.settings.wallet_apple_ca_certificate.read(),
            "certificate": order.event.settings.wallet_apple_certificate.read(),
            "key": order.event.settings.wallet_apple_key.read(),
            "password": order.event.settings.wallet_apple_key_password,
            "description": _("Ticket for {event} ({product})").format(  # TODO: i18n
                event=event.name, product=ticket
            ),
            "organizationName": event.organizer.name,
            "passTypeIdentifier": order.event.settings.wallet_apple_pass_type_id,
            "teamIdentifier": order.event.settings.wallet_apple_team_id,
            "serialNumber": serialNumber,
        })



        fields = self.get_pass_fields(layout, context)

        pkpass = SignedZipFile(
            context["ca_certificate"],
            context["certificate"],
            context["key"],
            context["password"],
        )
        strings = StringResource(locales=context["locales"])

        pass_json = self.generate_pass_json(fields, context, strings)
        print(pass_json)
        if fields["logo"]:
            logo = fields["logo"][0]["value"]
        else:
            logo = open(finders.find("pretix_passbook/logo.png"), "rb")

        if fields["icon"]:
            icon = fields["icon"][0]["value"]
        else:
            icon = open(finders.find("pretix_passbook/icon.png"), "rb")

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
    fieldgroups = [
        ImageFieldGroup(
            identifier="icon",
            name=_("Icon"),
            min_entries=0,
            max_entries=1,
            default_entries=[
                PlaceholderFieldEntry(
                    content="poweredby",
                )
            ],
            required=True
        ),
        ImageFieldGroup(
            identifier="logo",
            name=_("Logo"),
            min_entries=0,
            max_entries=1,
            default_entries=[
                PlaceholderFieldEntry(
                    content="poweredby",
                )
            ],
            required=True
        ),
        TextFieldGroup(
            identifier="logo_text",
            name=_("Logo text"),
            max_entries=1,
            display=FieldGroupDisplay.PLAIN,
            default_entries=[],
        ),
        TextFieldGroup(
            identifier="primary",
            name=_("Primary"),
            min_entries=1,
            max_entries=1,
            default_entries=[
                PlaceholderFieldEntry(
                    label=LazyI18nString({"de": "Tickettyp", "en": "Ticket type"}),
                    content="item",
                )
            ],  # TODO: support Lazyi18nproxy here
            description=_("These fields appear prominently featured on the pass."),
            required=True
        ),
        TextFieldGroup(
            identifier="secondary", name=_("Secondary"), max_entries=4
        ),  # TODO: validation of max field count if combined "Coupons, store cards, and generic passes with a square barcode can have a total of up to four secondary and auxiliary fields, combined."
        TextFieldGroup(identifier="header", name=_("Header"), max_entries=3),
        TextFieldGroup(identifier="auxiliary", name=_("Auxiliary"), max_entries=4),
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
        ),
        TextFieldGroup(identifier="back", name=_("Back")),
    ]
    preview_layout = [
        [
            {
                "children": [
                    {"fieldgroup": "logo", "relSize": 1},
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
