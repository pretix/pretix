from dataclasses import dataclass, field, asdict
from typing import Literal
import enum
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from i18nfield.strings import LazyI18nString

from pretix.base.pdf import get_images, get_variables
from .models import WalletLayout


class WalletPlatform:
    identifier: str
    name: str


class ApplePlatform(WalletPlatform):
    identifier = "apple"
    name = _("Apple")


class GooglePlatform(WalletPlatform):
    identifier = "google"
    name = _("Google")


class PlaceholderFieldType(enum.Enum):
    TEXT = "text"
    CODE = "qr"
    IMAGE = "image"
    PREDEFINED = "predefined"
    # TODO: POWERED_BY ?


@dataclass
class PlaceholderField:
    type: PlaceholderFieldType
    label: LazyI18nString
    content: str

    def asdict(self):
        return {"type": self.type.value, "label": self.label.data, "value": self.content}


@dataclass
class FieldGroupDefinition:
    name: str
    identifier: str
    entry_type: PlaceholderFieldType
    min_entries: int | None = None
    max_entries: int | None = None

    def asdict(self):
        return {
            "identifier": self.identifier,
            "name": self.name,
            "entry_type": self.entry_type.value,
            "min_entries": self.min_entries,
            "max_entries": self.max_entries,
        }


@dataclass
class PlaceholderFieldGroup(FieldGroupDefinition):
    entry_type: PlaceholderFieldType = PlaceholderFieldType.TEXT
    default_entries: list[PlaceholderField] = field(default_factory=list)

    def asdict(self):
        asdict = super().asdict()
        asdict["default_entries"] = [x.asdict() for x in self.default_entries]
        return asdict


@dataclass
class PredefinedFieldGroup(FieldGroupDefinition):
    entry_type: PlaceholderFieldType = PlaceholderFieldType.PREDEFINED
    min_entries = 0
    max_entries = 1


class PassStyle:
    identifier: str  # unique within platform
    name: str
    platform: Literal["apple"] | Literal["google"]
    fields: list[FieldGroupDefinition]
    # preview_image: str # TODO: preview

    def asdict(self):
        return {
            "identifier": self.identifier,
            "name": self.name,
            "platform": self.platform,
            "fields": [x.asdict() for x in self.fields],
        }


class AppleWalletEventTicket(PassStyle):
    identifier = "event_1"
    name = "Event Ticket Layout 1"
    platform = "apple"
    # order here limits in what order users can configure field "overspilling" (if too many fields are defined, where should the rest go) -> can only go down in the list
    # we evaluate the fields in this order, so they overspill in this order as well (fields from primary are appended to the overspilling field before fields from secondary are etc)
    fields = [
        PlaceholderFieldGroup(
            identifier="logo",
            name=_("Logo"),
            min_entries=1,
            max_entries=1,
            default_entries=[
                PlaceholderField(PlaceholderFieldType.IMAGE, LazyI18nString("logo"), "event:image")
            ],
            entry_type=PlaceholderFieldType.IMAGE,
        ),
        PlaceholderFieldGroup(
            identifier="primary",
            name=_("Primary"),
            min_entries=1,
            max_entries=1,
            default_entries=[
                PlaceholderField(PlaceholderFieldType.TEXT, LazyI18nString("Ticket type"), "item")
            ],
        ),
        PlaceholderFieldGroup(
            identifier="secondary", name=_("Secondary"), max_entries=4
        ),  # TODO: validation of max field count if combined "Coupons, store cards, and generic passes with a square barcode can have a total of up to four secondary and auxiliary fields, combined."
        PlaceholderFieldGroup(
            identifier="headers", name=_("Header"), max_entries=3
        ),  # TODO: header image
        PlaceholderFieldGroup(
            identifier="auxillary", name=_("Auxillary"), max_entries=4
        ),
        PlaceholderFieldGroup(identifier="back", name=_("Back")),
    ]
    # preview_image = "apple/event_ticket.svg"


class GoogleWalletEventTicket(PassStyle):
    identifier = "event"
    name = "Event Ticket"
    platform = "google"
    fields = [
        PredefinedFieldGroup(identifier="seating", name=_("Seating")),
        PlaceholderFieldGroup(
            identifier="qrcode", name=_("QR-Code"), entry_type=PlaceholderFieldType.CODE
        ),
    ]


AVAILABLE_PLATFORMS = {"apple": ApplePlatform, "google": GooglePlatform}
AVAILABLE_STYLES = [AppleWalletEventTicket(), GoogleWalletEventTicket()]


def get_platforms_with_styles():
    platforms_with_styles = {}
    for style in AVAILABLE_STYLES:
        platform = style.platform
        if platform not in platforms_with_styles:
            platforms_with_styles[platform] = {}
        platforms_with_styles[platform][style.identifier] = style
    return platforms_with_styles


def get_platform_styles(platform):
    platform_styles = {}
    for style in AVAILABLE_STYLES:
        if style.platform == platform:
            platform_styles[style.identifier] = style
    return platform_styles


def get_platforms():
    return AVAILABLE_PLATFORMS


class PassLayout:
    style: PassStyle
    layout: dict

    def __init__(self, style, layout):
        self.style = style
        self.layout = layout

    def validate(self, event):
        self.validate_fields(event)

    def validate_fields(self, event):
        placeholders = {"text": get_variables(event), "image": get_images(event)}

        style_fields = self.style.fields
        if "fields" not in self.layout:
            raise ValidationError(_("Layout did not contain any fields"))
        layout_fields = self.layout["fields"]
        if not isinstance(layout_fields, dict):
            raise ValidationError(_("'fields' must be dict"))

        for fieldgroup in style_fields:
            layout_field_data = layout_fields.get(fieldgroup.identifier, {})
            if fieldgroup.min_entries and fieldgroup.min_entries < len(
                layout_field_data.get('entries', [])
            ):
                raise ValidationError(
                    _("At least {min_entries} must be specified for {name}").format(
                        min_entries=fieldgroup.min_entries, name=fieldgroup.name
                    )
                )
            # TODO: move field validation to json schema
            for entry in layout_field_data.get('entries', []):
                if entry['type'] not in ('placeholder', fieldgroup.entry_type.value):
                    raise ValidationError(_("Placeholder of wrong type \"{type}\" in {name}").format(type=entry['type'], name="fieldgroup.name"))
                if entry['type'] == 'placeholder' and entry['content'] not in placeholders[fieldgroup.entry_type.value]:
                    raise ValidationError(_("Unknown placeholder {name}").format(name=entry['content']))