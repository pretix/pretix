import datetime
import io
import json
import time
import zipfile

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from i18nfield.strings import LazyI18nString

from pretix.base.models import CachedFile
from pretix.plugins.wallet.platforms.apple import (
    AppleWalletEventTicket, SignedZipFile, StringResource,
)


@pytest.fixture
def pkpass_context():
    key_pw = "TESTPW"
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

    ca_cert_pem = ca_cert.public_bytes(encoding=serialization.Encoding.PEM)
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(key_pw.encode()),
    )
    return {
        "ca_certificate": ca_cert_pem,
        "certificate": cert_pem,
        "key": key_pem,
        "password": key_pw,
    }


def get_file(content):
    val = SimpleUploadedFile(
        f"file-{time.time()}.dat", content, "application/octet-stream"
    )
    default_storage.save(val.name, val)
    val.close()
    return val


@pytest.fixture
def apple_env(env, pkpass_context):
    event, user, organizer = env
    event.settings.wallet_apple_ca_certificate = get_file(
        pkpass_context["ca_certificate"]
    )
    event.settings.wallet_apple_certificate = get_file(pkpass_context["certificate"])
    event.settings.wallet_apple_key = get_file(pkpass_context["key"])
    event.settings.wallet_apple_key_password = pkpass_context["password"]
    return event, user, organizer


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
        manifest = json.loads(zip_file.read("manifest.json"))
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


def get_value(strings, key):
    if key in strings.entries:
        return str(strings.entries[key])
    return key


BASIC_SAMPLE_LAYOUT = {
    "settings": {"bg_color": "#ff0000", "fg_color": "#00ff00", "label_color": "#0000ff"},
    "fieldgroups": {
        "primary": {
            "entries": [
                {"type": "placeholder", "label": "test", "content": "event_slug"},
                {
                    "label": {"de": "test-de", "en": "test-en"},
                    "type": "custom",
                    "content": "test content",
                },
            ]
        },
    }
}


@pytest.mark.django_db
def test_generate_pass_json(apple_env, order):
    event, user, organizer = apple_env

    layout = BASIC_SAMPLE_LAYOUT
    style = AppleWalletEventTicket(event, layout)
    style.validate()

    op = order.positions.first()
    fields = style.get_pass_fields(op)
    strings = StringResource(locales=["de", "en"])
    result = style.generate_pass_json(fields, op, strings)

    required_fields = [
        "description",
        "formatVersion",
        "organizationName",
        "passTypeIdentifier",
        "serialNumber",
        "teamIdentifier",
    ]
    for field in required_fields:
        assert field in result

    assert result["formatVersion"] == 1

    assert len(result["eventTicket"]["primaryFields"])
    assert (
        get_value(strings, result["eventTicket"]["primaryFields"][0]["value"])
        == "dummy"
    )
    assert (
        get_value(strings, result["eventTicket"]["primaryFields"][0]["label"]) == "test"
    )
    assert result["backgroundColor"] == "#ff0000"
    assert result["foregroundColor"] == "#00ff00"
    assert result["labelColor"] == "#0000ff"


@pytest.mark.django_db
def test_generate_pass_json_string_collision(apple_env, order):
    """check that string collisions are correctly prevented"""
    event, user, organizer = apple_env
    event.slug = "description"
    event.save()

    layout = BASIC_SAMPLE_LAYOUT
    style = AppleWalletEventTicket(event, layout)
    style.validate()

    op = order.positions.first()
    fields = style.get_pass_fields(op)
    strings = StringResource(locales=["de", "en"])
    result = style.generate_pass_json(fields, op, strings)

    assert "description" in strings.entries
    assert len(result["eventTicket"]["primaryFields"])
    assert (
        get_value(strings, result["eventTicket"]["primaryFields"][0]["value"])
        == "description"
    )


def read_escaped_string(strings):
    assert strings.startswith('"'), strings

    strings = strings[1:]
    key = ""
    escape = False
    i = 0
    for i, char in enumerate(strings, 1):
        assert char != "\n", "Newline in escaped string"
        if char == "\\":
            escape = True
        else:
            escape = False
        if escape:
            key += f"\\{char}".encode().decode("unicode-escape")
        elif char != '"':
            key += char
        else:
            break

    return strings[i:].lstrip(), key


def parse_strings(strings):
    data = {}
    while strings:
        strings = strings.lstrip()
        if strings.startswith("/*"):
            # comment, skin until end of comment
            strings = strings[2:]
            comment_end = strings.find("*/")
            if comment_end >= 0:
                strings = strings[comment_end:]
            else:
                strings = ""
        elif strings.startswith('"'):
            # string line, format circa '"key" = "value";\n'
            strings, key = read_escaped_string(strings)
            assert strings.startswith("=")
            strings = strings[1:].lstrip()
            strings, value = read_escaped_string(strings)
            assert strings.startswith(";")
            strings = strings[1:].lstrip()
            assert key not in data
            data[key] = value
        else:
            assert False, strings
    return data


def generate_and_get_pass(event, op, layout, expected_files=None, file_settings=None):
    style = AppleWalletEventTicket(event, layout, file_settings=file_settings)
    style.validate()

    name, content_type, data = style.generate(op)
    assert content_type == "application/vnd.apple.pkpass"
    with zipfile.ZipFile(io.BytesIO(data), "r") as f:
        assert not f.testzip()
        for name in expected_files or [
            "icon.png",
            "logo.png",
            "pass.json",
            "manifest.json",
            "signature",
        ]:
            assert name in f.namelist()

        pass_strings = {}
        for file in f.namelist():
            if (
                file.split("/")[0].endswith(".lproj")
                and file.split("/")[1] == "pass.strings"
            ):
                pass_strings[file.split(".")[0]] = parse_strings(f.read(file).decode())
        pass_data = json.loads(f.read("pass.json"))

    return pass_strings, pass_data


@pytest.mark.django_db
def test_generate_pass(apple_env, order):
    event, user, organizer = apple_env
    op = order.positions.first()

    pass_strings, pass_data = generate_and_get_pass(event, op, BASIC_SAMPLE_LAYOUT)

    def get_value(key):
        return pass_strings.get("en", next(iter(pass_strings.values())) or {}).get(
            key, key
        )

    assert len(pass_data["eventTicket"]["primaryFields"])
    assert get_value(pass_data["eventTicket"]["primaryFields"][0]["value"]) == "dummy"
    assert get_value(pass_data["eventTicket"]["primaryFields"][0]["label"]) == "test"
    assert pass_data["backgroundColor"] == "#ff0000"
    assert pass_data["foregroundColor"] == "#00ff00"
    assert pass_data["labelColor"] == "#0000ff"


@pytest.mark.django_db
def test_generate_pass_background_image_hack(apple_env, order):
    """
    iOS turns the text color white / very light gray when a background image is present, macOS does not.
    iOS respects the background color with transparent images (transparent pixels are shown in the backgroundColor), macOS turns transparent pixels black.

    To have consistent passes across platforms, we set the colors to always look the same-ish.
    """
    event, user, organizer = apple_env
    op = order.positions.first()

    c = CachedFile.objects.create(type="image/png", filename="test.png")
    c.file.save("test.png", ContentFile(open(finders.find("pretixplugins/wallet/icon.png"), "rb").read()))
    pass_strings, pass_data = generate_and_get_pass(event, op, BASIC_SAMPLE_LAYOUT, file_settings={"background": c.file}, expected_files=["background.png"])

    def get_value(key):
        return pass_strings.get("en", next(iter(pass_strings.values())) or {}).get(
            key, key
        )

    assert pass_data["backgroundColor"] == "#000000"
    assert pass_data["foregroundColor"] == "#ffffff"
    assert pass_data["labelColor"] == "#0000ff"
