import logging
import re
import subprocess
import tempfile
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.utils.translation import gettext_lazy as _
from pretix.control.forms import ClearableBasenameFileInput
from django.core.files import File
logger = logging.getLogger(__name__)


def validate_rsa_privkey(value: File):
    value = value.read().strip()
    if isinstance(value, bytes):
        value = value.decode()
    if not value:
        return
    if not re.match(r"^-----BEGIN( (RSA |ENCRYPTED )?PRIVATE KEY-----).*-----END\1$", value, re.DOTALL):
        raise ValidationError(
            _(
                "This does not look like an RSA private key in PEM format (it misses the correct begin or end signifiers)"
            ),
        )


class CertificateFileField(forms.FileField):
    widget = ClearableBasenameFileInput

    def clean(self, value, *args, **kwargs):
        value = super().clean(value, *args, **kwargs)
        if isinstance(value, UploadedFile):
            value.open("rb")
            value.seek(0)
            content = value.read()
            if (
                content.startswith(b"-----BEGIN CERTIFICATE-----")
                and b"-----BEGIN CERTIFICATE-----" in content
            ):
                return SimpleUploadedFile("cert.pem", content, "text/plain")

            openssl_cmd = [
                "openssl",
                "x509",
                "-inform",
                "DER",
                "-outform",
                "PEM",
            ]
            process = subprocess.Popen(
                openssl_cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
            process.stdin.write(content)
            pem, error = process.communicate()
            if process.returncode != 0:
                logger.info("Trying to convert a DER to PEM failed: {}".format(error))
                raise ValidationError(
                    _(
                        "This does not look like a X509 certificate in either PEM or DER format"
                    ),
                )

            return SimpleUploadedFile("cert.pem", pem, "text/plain")
        return value


class PNGImageField(forms.FileField):
    widget = ClearableBasenameFileInput

    def clean(self, value, *args, **kwargs):
        value = super().clean(value, *args, **kwargs)
        if isinstance(value, UploadedFile):
            try:
                from PIL import Image
            except ImportError:
                return value

            value.open("rb")
            value.seek(0)
            try:
                with (
                    Image.open(value, formats=settings.PILLOW_FORMATS_IMAGE) as im,
                    tempfile.NamedTemporaryFile("rb", suffix=".png") as tmpfile,
                ):
                    im.save(tmpfile.name)
                    tmpfile.seek(0)
                    return SimpleUploadedFile(
                        "picture.png", tmpfile.read(), "image png"
                    )
            except IOError:
                logger.exception("Could not convert image to PNG.")
                raise ValidationError(
                    _("The file you uploaded could not be converted to PNG format.")
                )

        return value
