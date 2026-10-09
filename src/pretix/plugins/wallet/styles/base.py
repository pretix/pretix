import enum
from typing import Any, Literal, TypedDict

import jsonschema
from django.core.exceptions import ValidationError
from django.core.files import File
from django.templatetags.static import static
from i18nfield.strings import LazyI18nString

from pretix.api.helpers import handle_file_upload
from pretix.base.models import OrderPosition

from ..i18n import MaybeTranslatedString, localizable_to_dict
from ..placeholders import (
    WalletPlaceholderRenderer, get_available_context,
    get_wallet_placeholder_renderer, get_wallet_placeholders,
)


class WalletPlatform:
    identifier: str
    name: str


class LayoutContext(TypedDict):
    placeholders: dict[str, dict]
    placeholder_renderer: WalletPlaceholderRenderer


class FieldGroupType(enum.Enum):
    PLACEHOLDER = "placeholder"
    PREDEFINED = "predefined"


class FieldGroupDisplay(enum.Enum):
    PLAIN = "plain"
    WITH_LABEL = "with_label"
    CODE = "code"


class FieldGroup:
    type: FieldGroupType
    identifier: str
    name: str
    description: str
    required: bool = False

    def __init__(self, identifier: str, name: str, description=None, required=False):
        self.identifier = identifier
        self.name = name
        self.required = required
        self.description = description or ""

    def layout_schema(
        self,
        remaining_fields: list["FieldGroup"],
        context: LayoutContext,
    ) -> dict:
        raise NotImplementedError()

    def asdict(self, locales: list[str], context: LayoutContext):
        return {
            "type": self.type.value,
            "identifier": self.identifier,
            "name": self.name,
            "description": self.description,
            "required": self.required,
        }


class FieldContentType(enum.Enum):
    IMAGE = "image"
    TEXT = "text"


class FieldEntryType(enum.Enum):
    CUSTOM = "custom"
    PLACEHOLDER = "placeholder"


class FieldEntry[T]:
    type: FieldEntryType
    label: MaybeTranslatedString | None
    content: T

    def __init__(
        self, type: FieldEntryType, content: T, label: MaybeTranslatedString | None = None
    ):
        self.type = type
        self.label = label
        self.content = content

    def asdict(self, locales: list[str]) -> dict:
        return {
            "type": self.type.value,
            "content": self.content,
            "label": localizable_to_dict(self.label, locales) if self.label is not None else None,
        }


class PlaceholderFieldEntry(FieldEntry[str]):
    type = FieldEntryType.PLACEHOLDER
    content: str

    def __init__(self, content: str, label: MaybeTranslatedString | None = None):
        self.label = label
        self.content = content


class CustomFieldEntry(FieldEntry[MaybeTranslatedString]):
    type: FieldEntryType
    content: MaybeTranslatedString

    def asdict(self, locales: list[str]) -> dict:
        return {
            "type": self.type.value,
            "content": localizable_to_dict(self.content, locales),
            "label": localizable_to_dict(self.label, locales) if self.label else None,
        }


class PredefinedFieldGroup(FieldGroup):
    type = FieldGroupType.PREDEFINED

    def layout_schema(
        self,
        remaining_fields: list["FieldGroup"],
        context: LayoutContext,
    ):
        return {"type": "object", "properties": {"active": {"type": "boolean"}}}


class PlaceholderFieldGroup(FieldGroup):
    type = FieldGroupType.PLACEHOLDER
    content_type: FieldContentType
    default_entries: list[FieldEntry]
    display: FieldGroupDisplay
    min_entries: int | None
    max_entries: int | None
    context_args: set[
        str
    ]  # what context arguments are available when rendering this fieldgroup

    def __init__(
        self,
        identifier: str,
        name: str,
        content_type: FieldContentType,
        description: str = "",
        required=False,
        default_entries=None,
        min_entries=None,
        max_entries=None,
        display=FieldGroupDisplay.WITH_LABEL,
        context_args: set[str] | None = None,
    ):
        super().__init__(identifier, name, description, required)
        self.content_type = content_type
        self.default_entries = default_entries or []
        self.min_entries = min_entries
        self.max_entries = max_entries
        self.display = display
        self.context_args = context_args or set()

        if self.required and (self.min_entries is None or self.min_entries < 1):
            self.min_entries = 1

    def asdict(self, locales: list[str], context: LayoutContext):
        return {
            **super().asdict(locales, context),
            "content_type": self.content_type.value,
            "default_entries": [x.asdict(locales) for x in self.default_entries],
            "display": self.display.value,
            "min_entries": self.min_entries,
            "max_entries": self.max_entries,
            "context_args": list(
                get_available_context(
                    self.context_args, context["placeholder_renderer"].transformations
                )
            ),
        }

    def layout_schema(
        self,
        remaining_fields: list["FieldGroup"],
        context: LayoutContext,
    ):
        content_type_placeholders = (
            context["placeholders"].get(self.content_type.value, {}).values()
        )
        renderer = context["placeholder_renderer"]
        available_placeholders = [
            x.identifier
            for x in content_type_placeholders
            if renderer.is_available(x, self.context_args)
        ]
        return {
            "type": "object",
            "properties": {
                "entries": self.entries_schema(placeholders=available_placeholders),
                "overflow": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "string",
                            "enum": [
                                f.identifier
                                for f in remaining_fields
                                if isinstance(f, PlaceholderFieldGroup)
                                and f.content_type == self.content_type
                            ],
                        },
                    ]
                },
            },
            "required": ["entries"],
        }

    def entries_schema(self, placeholders: list[str]):
        baseprops = {}
        if self.display == FieldGroupDisplay.WITH_LABEL:
            baseprops["label"] = {"$ref": "#/$defs/I18nString"}

        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "anyOf": [
                    {
                        "properties": {
                            **baseprops,
                            "type": {"const": "placeholder"},
                            "content": {"enum": placeholders},
                        }
                    },
                    {
                        "properties": {
                            **baseprops,
                            "type": {"const": "custom"},
                            "content": {"$ref": "#/$defs/I18nString"},
                        }
                    },
                ],
                "required": ["type", "content"],
            },
        }
        if self.display == FieldGroupDisplay.WITH_LABEL:
            schema["items"]["required"].append("label")
        if self.min_entries is not None:
            schema["minItems"] = self.min_entries
        # max_entries is not enforced here, as the layout can have more fields than that (null-fields are removed, rest is overspilled)
        return schema


class TextFieldGroup(PlaceholderFieldGroup):
    content_type = FieldContentType.TEXT

    def __init__(self, **kwargs):
        super().__init__(content_type=self.content_type, **kwargs)


class ImageFieldGroup(PlaceholderFieldGroup):
    content_type = FieldContentType.IMAGE
    display = FieldGroupDisplay.PLAIN

    def __init__(self, **kwargs):
        super().__init__(content_type=self.content_type, display=self.display, **kwargs)


SettingType = Literal["image", "text", "float", "color"]


class SettingsField:
    identifier: str
    label: str
    type: SettingType
    help_text: str | None
    required: bool
    default: str | None

    def asdict(self, locales: list[str]):
        return {
            "identifier": self.identifier,
            "label": self.label,
            "type": self.type,
            "help_text": self.help_text,
            "required": self.required,
            "default": self.default,
        }

    def layout_schema(self) -> dict[str, Any] | None:
        raise NotImplementedError()


class TextSettingsField(SettingsField):
    default: str | None

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


class ColorSettingsField(SettingsField):
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


class ImageSettingsField(SettingsField):
    _default: str | File | None

    def __init__(
        self,
        identifier: str,
        label: str,
        help_text: str | None = None,
        default: str | File | None = None,
    ):
        self.identifier = identifier
        self.label = label
        self.type = "image"
        self.help_text = help_text
        self.required = False
        self._default = default

    @property
    def default(self):
        if isinstance(self._default, str):
            return static(self._default)
        elif isinstance(self._default, File):
            return self._default.url

    def layout_schema(self):
        return


class FloatSettingsField(SettingsField):
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
        default: str | None = None,
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


class PassStyle:
    identifier: str  # unique within platform
    name: str

    def __init__(
        self, event, layout=None, file_settings: dict[str, File] | None = None
    ):
        self.event = event
        self.layout = layout
        self.file_settings = file_settings or {}
        self.placeholders = get_wallet_placeholders(self.event)

    @property
    def fieldgroups(self) -> list[FieldGroup]:
        # order here limits in what order users can configure field "overspilling" (if too many fields are defined, where should the rest go)
        #   -> can only go down in the list
        # we evaluate the fields in this order, so they overspill in this order as well
        return []

    @property
    def settings(self) -> list[SettingsField]:
        return []

    @property
    def preview_layout(self) -> list | None:
        return None

    @property
    def cleaned_settings(self):
        if not self.layout:
            return {}
        settings = {}
        for setting in self.settings:
            if isinstance(setting, ImageSettingsField):
                settings[setting.identifier] = self.file_settings.get(
                    setting.identifier
                )
                if not settings[setting.identifier] and setting.default:
                    settings[setting.identifier] = setting.default
            else:
                settings[setting.identifier] = self.layout.get("settings", {}).get(
                    setting.identifier, setting.default
                )
                if not settings[setting.identifier] and setting.default:
                    settings[setting.identifier] = setting.default
        return settings

    def asdict(self):  # -> dict[str, Any]:
        context = LayoutContext(
            placeholders=self.placeholders,
            placeholder_renderer=get_wallet_placeholder_renderer(),
        )
        return {
            "identifier": self.identifier,
            "name": self.name,
            "fieldgroups": [x.asdict(self.event.settings.locales, context) for x in self.fieldgroups],
            "preview_layout": self.preview_layout,
            "settings": [x.asdict(self.event.settings.locales) for x in self.settings],
        }

    def layout_schema(self):
        context = LayoutContext(
            placeholders=self.placeholders,
            placeholder_renderer=get_wallet_placeholder_renderer(),
        )
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            # TODO: $id
            "title": self.name,
            "type": "object",
            "properties": {
                "fieldgroups": {
                    "description": "Layout Field Groups",
                    "type": "object",
                    "properties": {
                        group.identifier: group.layout_schema(
                            context=context, remaining_fields=self.fieldgroups[i:]
                        )
                        for (i, group) in enumerate(self.fieldgroups)
                    },
                    "required": [
                        group.identifier for group in self.fieldgroups if group.required
                    ],
                },
                "settings": {
                    "type": "object",
                    "properties": {
                        setting.identifier: setting.layout_schema()
                        for setting in self.settings
                        if setting.layout_schema()
                    },
                    "required": [
                        setting.identifier
                        for setting in self.settings
                        if setting.required and setting.layout_schema()
                    ],
                },
            },
            "$defs": {
                "I18nString": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "object", "additionalProperties": {"type": "string"}},
                    ]
                }
            },
        }
        if any(group.required for group in self.fieldgroups):
            schema.setdefault("required", [])
            schema["required"].append("fieldgroups")
        if any(
            setting.required and setting.type == "text" for setting in self.settings
        ):
            schema.setdefault("required", [])
            schema["required"].append("settings")

        return schema

    def render_placeholder(self, context, content_type, content):
        placeholder = self.placeholders.get(content_type, {}).get(content)
        if placeholder:
            placeholder_value = context.render_placeholder(placeholder)
            if placeholder_value:
                return placeholder.label, placeholder_value

        return None, None

    def validate(self):
        schema = self.layout_schema()
        try:
            jsonschema.validate(self.layout, schema)
        except jsonschema.ValidationError as e:
            raise ValidationError("Invalid layout: {}".format(str(e)))

    def extract_file_settings(self, request, file_settings):
        res = {}
        for setting in self.settings:
            if setting.type == "image":
                if file_settings.get(setting.identifier) == "file:keep":
                    res[setting.identifier] = "keep"
                elif data := file_settings.get(setting.identifier):
                    res[setting.identifier] = handle_file_upload(
                        data,
                        request.user,
                        getattr(request, "auth", None),
                        {"image/png", "image/jpeg"},
                    )
                elif setting.identifier in file_settings:
                    res[setting.identifier] = None

        return res

    def get_pass_fields(self, op: OrderPosition):
        if not self.layout:
            raise ValueError("`layout` needs to be set")

        context = get_wallet_placeholder_renderer(order_position=op)

        fields = {}
        for group in self.fieldgroups:
            if isinstance(group, PredefinedFieldGroup):
                pass

            elif isinstance(group, PlaceholderFieldGroup):
                group_fields = fields.get(group.identifier, [])
                if group.identifier in self.layout["fieldgroups"]:
                    for field in self.layout["fieldgroups"][group.identifier][
                        "entries"
                    ]:
                        field_entry: dict[str, MaybeTranslatedString | None] = {}
                        if group.display == FieldGroupDisplay.WITH_LABEL:
                            field_entry["label"] = LazyI18nString(field["label"])
                        if field["type"] == FieldEntryType.PLACEHOLDER.value:
                            label, field_entry["value"] = self.render_placeholder(
                                context, group.content_type.value, field["content"]
                            )
                            if (
                                group.display == FieldGroupDisplay.WITH_LABEL
                                and not str(field_entry["label"])
                                and label
                            ):
                                field_entry["label"] = label

                        elif field["type"] == FieldEntryType.CUSTOM.value:
                            field_entry["value"] = LazyI18nString(field["content"])
                        if "value" in field_entry and field_entry["value"]:
                            group_fields.append(field_entry)
                if group.min_entries and len(group_fields) < group.min_entries:
                    raise ValueError(
                        f"Group {group.identifier} needs at least {group.min_entries} entries, but only {len(group_fields)} were provided"
                    )
                fields[group.identifier] = group_fields[: group.max_entries]
                if overflow_group := self.layout["fieldgroups"][group.identifier][
                    "overflow"
                ]:
                    fields.setdefault(overflow_group, [])
                    fields[overflow_group] += group_fields[group.max_entries :]

            else:
                raise ValueError("Unknown field group")
        return fields

    def group_is_active(self, identifier: str):
        if not self.layout:
            raise ValueError("`layout` needs to be set")

        return self.layout["fieldgroups"].get(identifier, {}).get("active", False)

    def generate(self, op: OrderPosition):
        raise NotImplementedError()
