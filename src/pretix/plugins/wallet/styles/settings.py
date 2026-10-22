import tempfile
from typing import Any, Callable, Literal, Protocol, runtime_checkable

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile
from django.forms import ValidationError
from django.templatetags.static import static
from django.utils.translation import gettext as _

SettingType = Literal["image", "text", "float", "color", "bool"]
JsonSerializable = int | bool | float | str | None


class SettingsField[T, I = T]:
    identifier: str
    label: str
    type: SettingType
    help_text: str | None
    required: bool
    default: Any | None

    def asdict(self, locales: list[str]):
        return {
            "identifier": self.identifier,
            "label": self.label,
            "type": self.type,
            "help_text": self.help_text,
            "required": self.required,
            "default": self.get_default(),
        }

    def layout_schema(self) -> dict[str, Any] | None:
        raise NotImplementedError()

    def get_default(self) -> JsonSerializable:
        if isinstance(self.default, JsonSerializable):
            return self.default
        elif self.default:
            raise NotImplementedError()

    def clean(self, value: I | None) -> T | None:
        if value:
            return value

        if self.default:
            return self.default


class TextSettingsField(SettingsField[str]):
    def __init__(
        self,
        identifier: str,
        label: str,
        help_text: str | None = None,
        required: bool = False,
        default: str | None = None,
    ):
        self.identifier = identifier
        self.label = label
        self.type = "text"
        self.help_text = help_text
        self.required = required
        self.default = default

    def layout_schema(self) -> dict[str, Any] | None:
        schema = {"type": "string"}
        if not self.required:
            schema = {"oneOf": [schema, {"type": "null"}]}
        return schema


class ColorSettingsField(SettingsField[str]):
    def __init__(
        self,
        identifier: str,
        label: str,
        help_text: str | None = None,
        required: bool = False,
        default: str | None = None,
    ):
        self.identifier = identifier
        self.label = label
        self.type = "color"
        self.help_text = help_text
        self.required = required
        self.default = default

    def layout_schema(self) -> dict[str, Any] | None:
        # TODO: validate that '#' + 6 hex chars
        schema = {"type": "string"}
        if not self.required:
            schema = {"oneOf": [schema, {"type": "null"}]}
        return schema


class FloatSettingsField(SettingsField[float]):
    min: float | None
    max: float | None

    def __init__(
        self,
        identifier: str,
        label: str,
        help_text=None,
        required: bool = False,
        min: float | None = None,
        max: float | None = None,
        default: float | None = None,
    ):
        self.type = "float"
        self.identifier = identifier
        self.label = label
        self.help_text = help_text
        self.required = required
        self.min = min
        self.max = max
        self.default = default

    def layout_schema(self):
        schema: dict[str, Any] = {"type": "number"}
        if self.min is not None:
            schema["minimum"] = self.min
        if self.max is not None:
            schema["maximum"] = self.max
        if not self.required:
            schema = {"oneOf": [schema, {"type": "null"}]}
        return schema

    def asdict(self, locales: list[str]):
        return super().asdict(locales) | {"min": self.min, "max": self.max}


class BooleanSettingsField(SettingsField[bool]):
    def __init__(
        self,
        identifier: str,
        label: str,
        help_text: str | None = None,
        default: bool = False,
    ):
        self.type = "bool"
        self.identifier = identifier
        self.label = label
        self.help_text = help_text
        self.required = False
        self.default = default

    def layout_schema(self):
        return {"type": "boolean"}


@runtime_checkable
class UrlAndReadFile(Protocol):
    url: str
    open: Callable
    seek: Callable
    read: Callable


class SettingsFile:
    url: str
    file: UrlAndReadFile

    def __init__(self, url, file):
        self.url = url
        self.file = file


class ImageSettingsField(SettingsField[SettingsFile, FieldFile]):
    default: str | UrlAndReadFile | None = None

    def __init__(
        self,
        identifier: str,
        label: str,
        help_text: str | None = None,
        default: str | UrlAndReadFile | None = None,
    ):
        self.identifier = identifier
        self.label = label
        self.type = "image"
        self.help_text = help_text
        self.required = False

        if isinstance(default, UrlAndReadFile):
            self.default = default
        elif isinstance(default, str):
            if not finders.find(default):
                raise ValueError(f"Unknown file: {default}")
            self.default = default
        elif default:
            raise ValueError("Unsupported `default`")

    def get_default(self):
        if isinstance(self.default, str):
            return static(self.default)
        elif isinstance(self.default, File):
            return self.default.url

    def layout_schema(self):
        return

    def clean(self, value):
        if value:
            return SettingsFile(value.url, value)

        if isinstance(self.default, UrlAndReadFile):
            return SettingsFile(self.default.url, self.default)

        if isinstance(self.default, str):
            return SettingsFile(static(self.default), File(None, finders.find(self.default)))


def convert_to_png(file: SettingsFile, max_size=None):
    # TODO: move validation to upload
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return file

    file.file.open("rb")
    file.file.seek(0)
    try:
        with (
            Image.open(file.file, formats=settings.PILLOW_FORMATS_IMAGE) as im,
            tempfile.NamedTemporaryFile("rb", suffix=".png") as tmpfile,
        ):
            im = ImageOps.exif_transpose(im)
            if max_size:
                im.thumbnail(max_size, resample=Image.Resampling.BICUBIC)
            im.save(tmpfile.name)
            tmpfile.seek(0)
            return SimpleUploadedFile("picture.png", tmpfile.read(), "image/png")
    except IOError:
        raise ValidationError(
            _("The file you uploaded could not be converted to PNG format.")
        )
