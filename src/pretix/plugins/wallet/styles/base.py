import enum
from i18nfield.strings import LazyI18nString
import jsonschema
from django.core.exceptions import ValidationError

class WalletPlatform:
    identifier: str
    name: str


class FieldGroupType(enum.Enum):
    PLACEHOLDER = "placeholder"
    PREDEFINED = "predefined"


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
        context: dict,
    ) -> dict:
        raise NotImplemented()

    def asdict(self):
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
    label: LazyI18nString | None
    content: T

    def __init__(
        self, type: FieldEntryType, content: T, label: LazyI18nString | None = None
    ):
        self.type = type
        self.label = label
        self.content = content

    def asdict(self) -> dict:
        return {"type": self.type.value, "content": self.content, "label": self.label.data if self.label else None}

class PlaceholderFieldEntry(FieldEntry[str]):
    type = FieldEntryType.PLACEHOLDER
    label: LazyI18nString | None
    content: str

    def __init__(
        self, content: str, label: LazyI18nString | None = None
    ):
        self.label = label
        self.content = content


class CustomFieldEntry(FieldEntry[LazyI18nString]):
    type: FieldEntryType
    label: LazyI18nString | None
    content: LazyI18nString

    def asdict(self) -> dict:
        return {"type": self.type.value, "content": self.content.data, "label": self.label.data if self.label else None}



class PredefinedFieldGroup(FieldGroup):
    type = FieldGroupType.PREDEFINED

    def layout_schema(
        self,
        remaining_fields: list["FieldGroup"],
        context: dict,
    ):
        return {
            "type": "object"
        }

class PlaceholderFieldGroup(FieldGroup):
    type = FieldGroupType.PLACEHOLDER
    content_type: FieldContentType
    default_entries: list[FieldEntry]
    labels: bool
    min_entries: int | None
    max_entries: int | None

    def __init__(
        self,
        identifier: str,
        name: str,
        content_type: FieldContentType,
        description: str=None,
        required=False,
        default_entries=None,
        min_entries=None,
        max_entries=None,
        labels=True,
    ):
        super().__init__(identifier, name, description, required)
        self.content_type = content_type
        self.default_entries = default_entries or []
        self.min_entries = min_entries
        self.max_entries = max_entries
        self.labels = labels

        if self.required and (self.min_entries is None or self.min_entries < 1):
            self.min_entries = 1

    def asdict(self):
        return {
            **super().asdict(),
            "content_type": self.content_type.value,
            "default_entries": [x.asdict() for x in self.default_entries],
            "labels": self.labels,
            "min_entries": self.min_entries,
            "max_entries": self.max_entries,
        }

    def layout_schema(
        self,
        remaining_fields: list["FieldGroup"],
        context: dict,
    ):
        placeholders = list(context.get("placeholders", {}).get(self.content_type.value, {}).keys())
        return {
            "type": "object",
            "properties": {
                "entries": self.entries_schema(placeholders=placeholders),
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
        if self.labels:
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
        if self.labels:
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

    def __init__(self, **kwargs):
        super().__init__(content_type=self.content_type, **kwargs)


class PassStyle:
    platform: type[WalletPlatform]
    identifier: str  # unique within platform
    name: str
    # order here limits in what order users can configure field "overspilling" (if too many fields are defined, where should the rest go) -> can only go down in the list
    # we evaluate the fields in this order, so they overspill in this order as well (fields from primary are appended to the overspilling field before fields from secondary are etc)

    fieldgroups: list[FieldGroup]

    def asdict(self):
        return {
            "platform": self.platform.identifier,
            "identifier": self.identifier,
            "name": self.name,
            "fieldgroups": [x.asdict() for x in self.fieldgroups],
        }

    def layout_schema(self, context):
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
                }
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
            schema["required"] = ["fieldgroups"]

        return schema

    def generate(self, layout, context):
        raise NotImplementedError()

    def render_placeholder(self, context, content_type, content):
        placeholder = (
            context.get("placeholders")
            .get(content_type, {})
            .get(content)
        )
        if placeholder:
            placeholder_value = placeholder["evaluate"](
                *context.get("evaluation_context", [])
            )
            if placeholder_value:
                return placeholder["label"], placeholder_value

        return None, None

    def get_pass_fields(self, layout, context):
        fields = {}
        for group in self.fieldgroups:
            if isinstance(group, PredefinedFieldGroup):
                pass
            elif isinstance(group, PlaceholderFieldGroup):
                group_fields = fields.get(group.identifier, [])
                if group.identifier in layout["fieldgroups"]:
                    for field in layout["fieldgroups"][group.identifier]["entries"]:
                        field_entry = {}
                        if group.labels:
                            field_entry["label"] = LazyI18nString(field["label"])
                        if field["type"] == FieldEntryType.PLACEHOLDER.value:
                            label, field_entry["value"] = self.render_placeholder(context, group.content_type.value, field['content'])
                            if group.labels and not str(field_entry['label']) and label:
                                field_entry['label'] = LazyI18nString(label)

                        elif field["type"] == FieldEntryType.CUSTOM.value:
                            field_entry["value"] = LazyI18nString(field["content"])
                        if "value" in field_entry and field_entry["value"]:
                            group_fields.append(field_entry)
                if group.min_entries and len(group_fields) < group.min_entries:
                    raise ValueError(
                        f"Group {group.identifier} needs at least {group.min_entries} entries, but only {len(group_fields)} were provided"
                    )
                fields[group.identifier] = group_fields[: group.max_entries]
                if (overflow_group := layout["fieldgroups"][group.identifier]['overflow']):
                    fields.setdefault(overflow_group, [])
                    fields[overflow_group] += group_fields[group.max_entries:]
            else:
                raise ValueError("Unknown field group")
        return fields


class PassLayout:
    style: PassStyle
    layout: dict

    def __init__(self, style, layout):
        self.style = style
        self.layout = layout

    def validate(self, context):
        schema = self.style.layout_schema(context)
        try:
            jsonschema.validate(self.layout, schema)
        except jsonschema.ValidationError as e:
            raise ValidationError("Invalid layout: {}".format(str(e)))

    def generate(self, context):
        # TODO: how to handle nonexisting placeholders here?
        self.validate(context)
        return self.style.generate(self.layout, context)