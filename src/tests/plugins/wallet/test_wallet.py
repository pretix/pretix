from pretix.plugins.wallet.styles.base import (
    PassStyle,
    WalletPlatform,
    PlaceholderFieldGroup,
    FieldContentType,
    PassLayout,
    FieldGroupType,
    FieldEntryType,
)
from pretix.plugins.wallet.styles.apple import SignedZipFile, StringResource
from django.utils.translation import gettext as _
import jsonschema
import pytest
from i18nfield.strings import LazyI18nString
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography import x509
import datetime
import io
import zipfile
import json


class WalletTestPlatform(WalletPlatform):
    identifier = "test_platform"
    name = _("Test Wallet Platform")


class MinimalTestStyle(PassStyle):
    platform = WalletTestPlatform
    identifier = "test_style"
    name = _("Test Wallet Style")
    fieldgroups = []


class TicketTestStyle(PassStyle):
    platform = WalletTestPlatform
    identifier = "test_ticket"
    name = _("Test Wallet Style Ticket")
    fieldgroups = [
        PlaceholderFieldGroup(
            identifier="text1",
            name=_("Text 1"),
            content_type=FieldContentType.TEXT,
            required=True,
        ),
        PlaceholderFieldGroup(
            identifier="text2",
            name=_("Text 2"),
            content_type=FieldContentType.TEXT,
            required=False,
            labels=False,
        ),
        PlaceholderFieldGroup(
            identifier="image1",
            name=_("Image 1"),
            content_type=FieldContentType.IMAGE,
            required=False,
            labels=False,
        ),
    ]

    def generate(self, layout, context):
        output = f"Generated Pass: {self.name}\n\n"
        for group in self.fieldgroups:
            if group.identifier in layout["fieldgroups"]:
                output += f"Group: {group.name}\n"
                if group.type == FieldGroupType.PREDEFINED:
                    output += "PREDEFINED\n"
                else:
                    for field in layout["fieldgroups"][group.identifier]["entries"]:
                        if group.labels:
                            label = LazyI18nString(field["label"])
                            output += f"{label}: "
                        if field["type"] == FieldEntryType.PLACEHOLDER.value:
                            placeholder = (
                                context.get("placeholders")
                                .get(group.content_type.value, {})
                                .get(field["content"])
                            )
                            if placeholder:
                                output += placeholder["evaluate"](
                                    *context.get("evaluation_context", [])
                                )
                            else:
                                output += f"UNKNOWN: {field['content']}"
                        elif field["type"] == FieldEntryType.TEXT.value:
                            output += str(LazyI18nString(field["content"]))
                        elif field["type"] == FieldEntryType.IMAGE.value:
                            output += f"<IMG>{field['content']}</IMG>"
                        output += "\n"
                output += "\n"
        return output


@pytest.fixture
def layout_context():
    return {
        "placeholders": {
            "text": {"test_placeholder": {"evaluate": lambda: "test placeholder"}}
        }
    }


def test_schema_generation_minimal():
    style = MinimalTestStyle()
    context = {}
    schema = style.layout_schema(context)
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "fieldgroups" in schema["properties"]

    jsonschema.validate({}, schema)
    jsonschema.validate({"fieldgroups": {}}, schema)


def test_schema_ticket_generation(layout_context):
    style = TicketTestStyle()
    schema = style.layout_schema(layout_context)
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "fieldgroups" in schema["properties"]


@pytest.mark.parametrize(
    "layout",
    [
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": {"de": "test-de", "en": "test-en"},
                            "content": "test_placeholder",
                        }
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {"type": "text", "label": "test", "content": "test content"}
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": {"de": "test-de", "en": "test-en"},
                            "content": "test_placeholder",
                        },
                        {"type": "text", "label": "test", "content": "test content"},
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": {"de": "test-de", "en": "test-en"},
                            "content": "test_placeholder",
                        },
                        {"type": "text", "label": "test", "content": "test content"},
                    ],
                    "overflow": "text2",
                }
            }
        },
    ],
)
def test_schema_ticket_valid(layout_context, layout):
    style = TicketTestStyle()
    schema = style.layout_schema(layout_context)

    jsonschema.validate(layout, schema)


@pytest.mark.parametrize(
    "layout",
    [
        {},
        {"fieldgroups": {}},
        {"fieldgroups": {"text1": {}}},
        {"fieldgroups": {"text1": {"entries": []}}},
        {"fieldgroups": {"text1": {"overflow": "test"}}},
        {
            "fieldgroups": {
                "text1": {
                    "entries": [{"type": "placeholder", "content": "test_placeholder"}]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": [],
                            "content": "test_placeholder",
                        }
                    ]
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {"entries": [{"type": "text", "content": "test content"}]}
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                    "overflow": "invalid_group",
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                    "overflow": "image1",
                }
            }
        },
        {
            "fieldgroups": {
                "text1": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                },
                "text2": {
                    "entries": [
                        {
                            "type": "placeholder",
                            "label": "test",
                            "content": "test_placeholder",
                        }
                    ],
                    "overflow": "text1",
                },
            }
        },
    ],
)
def test_schema_ticket_invalid(layout_context, layout):
    style = TicketTestStyle()
    schema = style.layout_schema(layout_context)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(layout, schema)


def test_style_representation():
    style = TicketTestStyle()
    style_dict = style.asdict()
    assert style_dict["platform"] == "test_platform"
    assert style_dict["identifier"] == "test_ticket"
    assert style_dict["name"] == _("Test Wallet Style Ticket")

    assert style_dict["fieldgroups"][0]["identifier"] == "text1"
    assert style_dict["fieldgroups"][0]["name"] == "Text 1"
    assert style_dict["fieldgroups"][0]["content_type"] == "text"
    assert style_dict["fieldgroups"][0]["labels"] == True
    assert style_dict["fieldgroups"][0]["required"] == True


def test_layout_generate(layout_context):
    style = TicketTestStyle()
    layout = {
        "fieldgroups": {
            "text1": {
                "entries": [
                    {
                        "type": "placeholder",
                        "label": {"de": "test-de", "en": "test-en"},
                        "content": "test_placeholder",
                    },
                    {"type": "text", "label": "test", "content": "test content"},
                ],
                "overflow": "text2",
            }
        }
    }

    pass_layout = PassLayout(style, layout)
    generated_pass = pass_layout.generate(layout_context)

    assert (
        generated_pass
        == "Generated Pass: Test Wallet Style Ticket\n\nGroup: Text 1\ntest-en: test placeholder\ntest: test content\n\n"
    )


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

