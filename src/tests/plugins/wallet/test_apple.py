from pretix.plugins.wallet.styles.apple import SignedZipFile, StringResource, AppleWalletEventTicket
from django.utils.translation import gettext as _
import pytest
from i18nfield.strings import LazyI18nString
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography import x509
import datetime
import io
import zipfile
import json
import jsonschema


@pytest.fixture
def pkpass_context():
    key_pw = b"TESTPW"
    now = datetime.datetime.now()
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "TTDR")])
        )
        .issuer_name(
            x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "ROOT Inc.")])
        )
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )

    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "UID=pass.test.test")]
            )
        )
        .issuer_name(
            x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "TTDR")])
        )
        .public_key(key.public_key())
        .serial_number(2)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )

    ca_cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(key_pw),
    )
    return {
        "ca_certificate": ca_cert_pem,
        "certificate": cert_pem,
        "key": key_pem,
        "password": key_pw,
    }


def test_signed_zip(pkpass_context):
    pkpass = SignedZipFile(**pkpass_context)
    generated_pass = pkpass.finish()

    with zipfile.ZipFile(io.BytesIO(generated_pass), "r") as zip_file:
        assert set(zip_file.namelist()) == {"manifest.json", "signature"}
        with zip_file.open("manifest.json") as f:
            manifest = json.load(f)
        assert manifest == {}

        with zip_file.open("signature") as f:
            signature = f.read()

        assert signature

    pkpass = SignedZipFile(**pkpass_context)
    pkpass.add_file("test", b"test content")
    generated_pass = pkpass.finish()

    with zipfile.ZipFile(io.BytesIO(generated_pass), "r") as zip_file:
        assert set(zip_file.namelist()) == {"test", "manifest.json", "signature"}
        with zip_file.open("manifest.json") as f:
            manifest = json.load(f)
        assert manifest == {"test": "1eebdf4fdc9fc7bf283031b93f9aef3338de9052"}

        with zip_file.open("signature") as f:
            signature = f.read()

        assert signature

    pkpass = SignedZipFile(**pkpass_context)
    pkpass.add_file("test/test", "test content")
    generated_pass = pkpass.finish()

    with zipfile.ZipFile(io.BytesIO(generated_pass), "r") as zip_file:
        assert set(zip_file.namelist()) == {"test/test", "manifest.json", "signature"}
        with zip_file.open("manifest.json") as f:
            manifest = json.load(f)
        assert manifest == {"test/test": "1eebdf4fdc9fc7bf283031b93f9aef3338de9052"}

        with zip_file.open("signature") as f:
            signature = f.read()

        assert signature


def test_stringresource_minimal():
    resource = StringResource(locales=["de", "en"])
    resource.add_entry("TEST", LazyI18nString({"de": "test-de", "en": "test-en"}))
    stringfiles = resource.generate()

    assert stringfiles.keys() == {"de", "en"}
    assert stringfiles["de"] == '"TEST" = "test-de";'
    assert stringfiles["en"] == '"TEST" = "test-en";'


@pytest.mark.parametrize(
    "input,output",
    [
        ['te"st', 'te\\"st'],
        ["te\rst", "te\\rst"],
        ["te\nst", "te\\nst"],
        ["te\r\nst", "te\\r\\nst"],
        ["te\r\nst", "te\\r\\nst"],
        ["te\\st", "te\\\\st"],
    ],
)
def test_stringresource_escaping(input, output):
    resource = StringResource(locales=["en"])
    resource.add_entry("TEST", LazyI18nString({"en": input}))
    stringfiles = resource.generate()

    assert stringfiles.keys() == {"en"}
    assert stringfiles["en"] == f'"TEST" = "{output}";'

    resource = StringResource(locales=["en"])
    resource.add_entry(input, LazyI18nString({"en": "test"}))
    stringfiles = resource.generate()

    assert stringfiles.keys() == {"en"}
    assert stringfiles["en"] == f'"{output}" = "test";'



def test_stringresource_additional_locale():
    resource = StringResource(locales=["de", "en", "fr"])
    resource.add_entry("TEST", LazyI18nString({"de": "test-de", "en": "test-en"}))
    stringfiles = resource.generate()

    assert stringfiles.keys() == {"de", "en", "fr"}
    assert stringfiles["de"] == '"TEST" = "test-de";'
    assert stringfiles["en"] == '"TEST" = "test-en";'
    assert stringfiles["fr"] == '"TEST" = "test-en";'

def test_generate_pass_json():
    context = {
        "placeholders": {
            "text": {"test_placeholder": {"evaluate": lambda: "test placeholder"}}
        },
        "description": "Ticket for Test",
        "organizationName": "TestOrg",
        "serialNumber": "1",
        "passTypeIdentifier": "pass.test.test",
        "teamIdentifier": "ABCDEF123456"
    }
    layout = {"fieldgroups": {"primary": {"entries": [{"type": "placeholder", "label": "test", "content": "test_placeholder"}, {"type": "text", "label": {"de":"test-de", "en": "test-en"}, "content": "test content"}]}}}
    style = AppleWalletEventTicket()
    schema = style.layout_schema(context)
    jsonschema.validate(schema, layout)

    result = style.generate_pass_json(layout, context)

    required_fields = ["description", "formatVersion", "organizationName", "passTypeIdentifier", "serialNumber", "teamIdentifier"]
    for field in required_fields:
        assert field in result

    assert result['formatVersion'] == 1

    breakpoint()