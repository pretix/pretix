from .base import (
    FieldEntryType,
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
import cryptography.hazmat.primitives.serialization.pkcs7
import json
from django.contrib.staticfiles import finders


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

    def __init__(self, ca_certificate, certificate, key, password):
        self.ca_certificate = cryptography.x509.load_pem_x509_certificate(
            ca_certificate
        )
        self.certificate = cryptography.x509.load_pem_x509_certificate(certificate)
        self.key = cryptography.hazmat.primitives.serialization.load_pem_private_key(
            key, password
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
    platform = ApplePlatform

    def pass_content(self, layout, context, strings):
        raise NotImplementedError()

    def generate_pass_json(self, layout, context, strings):
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
            **self.pass_content(layout, context, strings),
        }
        return pass_json

    def generate(self, layout, context):
        for key in ["ca_certificate", "certificate", "key", "password", "locales"]:
            if key not in context:
                raise ValueError(f"{key} missing from context")
        pkpass = SignedZipFile(
            context["ca_certificate"],
            context["certificate"],
            context["key"],
            context["password"],
        )
        strings = StringResource(locales=context['locales'])

        pass_json = self.generate_pass_json(layout, context, strings)
        print(pass_json)
        pkpass.add_file(
                "icon.png", open(finders.find("pretix_passbook/icon.png"), "rb").read()
            )

        pkpass.add_file("pass.json", json.dumps(pass_json))
        return pkpass.finish()


class AppleWalletEventTicket(AppleWalletStyle):
    identifier = "event_1"
    name = _("Event Ticket Layout 1")
    fieldgroups = [
        ImageFieldGroup(
            identifier="logo",
            name=_("Logo"),
            min_entries=0,
            max_entries=1,
            labels=False,
            default_entries=[
                PlaceholderFieldEntry(
                    content="poweredby",
                )
            ],
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

    def get_pass_fields(self, layout, context):
        fields = {}
        for group in self.fieldgroups:
            if isinstance(group, PredefinedFieldGroup):
                pass
            elif isinstance(group, PlaceholderFieldGroup):
                group_fields = []
                if group.identifier in layout["fieldgroups"]:
                    for field in layout["fieldgroups"][group.identifier]["entries"]:
                        field_entry = {}
                        if group.labels:
                            field_entry["label"] = LazyI18nString(field["label"])
                        if field["type"] == FieldEntryType.PLACEHOLDER.value:
                            placeholder = (
                                context.get("placeholders")
                                .get(group.content_type.value, {})
                                .get(field["content"])
                            )
                            if placeholder:
                                placeholder_value = placeholder["evaluate"](
                                    *context.get("evaluation_context", [])
                                )
                                if placeholder_value:
                                    field_entry["value"] = placeholder_value
                        elif field["type"] == FieldEntryType.TEXT.value:
                            placeholder_value = LazyI18nString(field["content"])
                        elif field["type"] == FieldEntryType.IMAGE.value:
                            raise NotImplementedError(
                                "Image placeholders not implemented"
                            )
                        if "value" in field_entry and field_entry["value"]:
                            group_fields.append(field_entry)
                if group.min_entries and len(group_fields) < group.min_entries:
                    raise ValueError(
                        f"Group {group.identifier} needs at least {group.min_entries} entries, but only {len(group_fields)} were provided"
                    )
                fields[group.identifier] = group_fields[: group.max_entries]
            else:
                raise ValueError("Unknown field group")
        return fields

    def convert_fields(self, strings, fields, prefix):
        converted = []
        for i,f in enumerate(fields):
            converted_field = {**f, "key": f"{prefix}-{i}"}
            if "label" in converted_field and isinstance(converted_field['label'], LazyI18nString):
                strings.add_entry(f"{prefix}-{i}-label", converted_field['label'])
                converted_field['label'] = f"{prefix}-{i}-label"

            converted.append(converted_field)
        return converted

    def pass_content(self, layout, context, strings):
        fields = self.get_pass_fields(layout, context)
        return {
            "eventTicket": {
                "primaryFields": self.convert_fields(strings, fields['primary'], 'primary')
            }
        }
