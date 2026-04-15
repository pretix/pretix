from .base import (
    FieldEntry,
    FieldEntryType,
    FieldContentType,
    ImageFieldGroup,
    PlaceholderFieldGroup,
    TextFieldGroup,
    WalletPlatform,
    PassStyle,
    PlaceholderFieldEntry,
    CustomFieldEntry,
)
from django.utils.translation import gettext as _
from i18nfield.strings import LazyI18nString
import io
import hashlib
import zipfile
import cryptography
import cryptography.hazmat.primitives.serialization.pkcs7
# from cryptography import x509
# from cryptography.hazmat.primitives import hashes, serialization
# from cryptography.hazmat.primitives.serialization import pkcs7
import json

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

    def add_entry(self, key: str, value: LazyI18nString): # TODO: replace LazyI18nString with dict or handle strings where data == ""
        if key in self.entries:
            raise ValueError(f"{key} already exists in this StringResource")
        self.entries[key] = value
        if isinstance(value.data, dict):
            self.locales |= value.data.keys()

    def escape(self, string):
        return string.translate(str.maketrans({"\"": "\\\"", "\r": "\\r", "\n": "\\n", "\\": "\\\\"}))
    def generate_resource(self, language):
        output = ""
        for key, entry in self.entries.items():
            output += f'"{self.escape(key)}" = "{self.escape(entry.localize(language))}";\n'
        return output.strip()
    
    def generate(self):
        return {language: self.generate_resource(language) for language in self.locales}
            


class SignedZipFile:
    """ Generates a zip-file with manifest and signature as apple expects a pkpass file to be """
    def __init__(self, ca_certificate, certificate, key, password):
        self.ca_certificate = cryptography.x509.load_pem_x509_certificate(ca_certificate)
        self.certificate = cryptography.x509.load_pem_x509_certificate(certificate)
        self.key = cryptography.hazmat.primitives.serialization.load_pem_private_key(key, password)
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

    def generate_pass_json(self, layout, context):
        pass_json = {}
        return pass_json
    
    def generate(self, layout, context):
        for key in ["certificate", "key", "wwdr_certificate", "password"]:
            if key not in context:
                raise ValueError(f"{key} missing from context")
        pkpass = SignedZipFile(
            context["certificate"],
            context["key"],
            context["wwdr_certificate"],
            context["password"],
        )

        pass_json = self.generate_pass_json()
        pkpass.add_file("pass.json", json.dumps(pass_json))
        return pkpass.finish()


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
