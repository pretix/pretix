import hashlib
import io
import json
import logging
import zipfile

import cryptography
import cryptography.hazmat.primitives.hashes
import cryptography.hazmat.primitives.serialization.pkcs7
import cryptography.x509
from django.utils.encoding import force_bytes
from django.utils.translation import gettext as _

from pretix.plugins.wallet.i18n import (
    MaybeTranslatedString,
)
from ..base import (
    WalletPlatform,
)

from django import forms
from django.utils.translation import gettext as _

from pretix.base.forms import SecretKeySettingsField
from pretix.control.forms import ClearableBasenameFileInput

from ...forms import CertificateFileField, validate_rsa_privkey

logger = logging.getLogger("pretix.plugins.wallet.apple")


class ApplePlatform(WalletPlatform):
    identifier = "apple"
    name = _("Apple Wallet")

    @classmethod
    def get_global_settings(cls, **kwargs):
        return OrderedDict(
            [
                (
                    # TODO: extract from pass certificate
                    "wallet_apple_team_id",
                    forms.CharField(
                        label=_("Apple Wallet Pass team ID"),
                        required=False,
                    ),
                ),
                (
                    # TODO: extract from pass certificate
                    "wallet_apple_pass_type_id",
                    forms.CharField(
                        label=_("Apple Wallet Pass type"),
                        required=False,
                    ),
                ),
                (
                    "wallet_apple_certificate",
                    CertificateFileField(
                        label=_("Apple Wallet Pass certificate file"),
                        required=False,
                    ),
                ),
                (
                    # TODO: download this server-side
                    "wallet_apple_ca_certificate",
                    CertificateFileField(
                        label=_("Apple Wallet Pass CA Certificate"),
                        help_text=_(
                            "You can download the current CA certificate from apple at "
                            "https://www.apple.com/certificateauthority/AppleWWDRCAG4.cer"
                        ),
                        required=False,
                    ),
                ),
                (
                    "wallet_apple_key",
                    forms.FileField(
                        label=_("Apple Wallet Pass secret key"),
                        required=False,
                        validators=[validate_rsa_privkey],
                        widget=ClearableBasenameFileInput,
                    ),
                ),
                (
                    "wallet_apple_key_password",
                    SecretKeySettingsField(
                        label=_("Apple Wallet Pass key password"),
                        required=False,
                        help_text=_(
                            "Optional, only necessary if the key entered above requires a password to use."
                        ),
                    ),
                ),
            ]
        )

    # TODO: generate_ops
    # def generate_order(self, order: Order):
    #     with tempfile.TemporaryFile() as d:
    #         with zipfile.ZipFile(d, "w") as zipf:
    #             for pos in order.positions_with_tickets:
    #                 fname, __, content = self.generate(pos)
    #                 zipf.writestr(
    #                     "{}-{}{}".format(
    #                         order.code, pos.positionid, os.path.splitext(fname)[1]
    #                     ),
    #                     content,
    #                 )

    #         d.seek(0)
    #         return (
    #             "{}-{}.pkpasses".format(order.code, self.identifier),
    #             "application/vnd.apple.pkpasses",
    #             d.read(),
    #         )


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
        return self.file.getvalue(), manifest.decode()

    def add_file(self, filename: str, content: str | bytes):
        if isinstance(content, str):
            content = content.encode()

        with self.zip_file.open(filename, "w") as f:
            f.write(content)
        self.manifest[filename] = hashlib.sha1(content).hexdigest()
