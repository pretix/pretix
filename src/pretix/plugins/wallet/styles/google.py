import uuid
from functools import cached_property
from urllib.parse import urljoin

from django.conf import settings
from django.db import transaction
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from walletobjects import ButtonJWT, EventTicketClass, EventTicketObject
from walletobjects.comms import Comms
from walletobjects.constants import (
    AnimationType,
    Barcode,
    ClassType,
    ConfirmationCode,
    DoorsOpen,
    MultipleDevicesAndHoldersAllowedStatus,
    ObjectState,
    ObjectType,
    ReviewStatus,
)

from pretix.base.models import Event, OrderPosition
from pretix.base.settings import GlobalSettingsObject
from pretix.multidomain.urlreverse import eventreverse_absolute
from pretix.plugins.wallet.i18n import localizable_to_dict
from pretix.plugins.wallet.models import GoogleWalletInstance, GoogleWalletType
from pretix.plugins.wallet.styles.base import (
    BooleanSettingsField,
    ColorSettingsField,
    FieldGroup,
    FieldGroupDisplay,
    FloatSettingsField,
    ImageSettingsField,
    PassStyle,
    PlaceholderFieldEntry,
    PredefinedFieldGroup,
    TextFieldGroup,
    WalletPlatform,
)


def _get_instance_uuid():
    gs = GlobalSettingsObject()
    if not gs.settings.wallet_google_instance_uuid:
        gs.settings.wallet_google_instance_uuid = str(uuid.uuid4())

    return gs.settings.wallet_google_instance_uuid


def get_class_id(event: Event, op: OrderPosition):
    instance_uuid = _get_instance_uuid()
    issuer_id = event.settings.get("wallet_google_issuer_id")
    return "%s.pretix-%s-%s-%s-%s-%s" % (
        issuer_id,
        instance_uuid,
        event.organizer.slug,
        event.slug,
        op.item_id,
        op.variation_id or 0,
    )


def get_object_id(op: OrderPosition):
    instance_uuid = _get_instance_uuid()
    issuer_id = op.order.event.settings.get("wallet_google_issuer_id")

    return "%s.pretix-%s-%s-%s-%s-%s-1" % (
        issuer_id,
        instance_uuid,
        op.order.event.organizer.slug,
        op.order.event.slug,
        op.order.code,
        op.positionid,
    )


def get_translated_dict(string, locales):
    translated = {}

    for locale in locales:
        translation.activate(locale)
        translated[locale] = _(string)
        translation.deactivate()

    return translated


def get_translated_string(string, locale):
    translation.activate(locale)
    translated = _(string)
    translation.deactivate()

    return translated


class GooglePlatform(WalletPlatform):
    identifier = "google"
    name = _("Google")


class GoogleWalletEventTicketStyle(PassStyle):
    platform = GooglePlatform

    @cached_property
    def comms(self):
        return Comms(self.event.settings.get("wallet_google_credentials").read())

    def put_item_cached(self, instance_type, item_type, object):
        with transaction.atomic():
            instance, created = GoogleWalletInstance.objects.get_or_create(
                event=self.event,
                type=instance_type,
                identifier=object["id"],
                defaults={"data": object},
            )
            if created or instance.data != object:
                result = self.comms.put_item(item_type, object["id"], object)
                instance.data = object
                instance.save(update_fields=["data"])
                return result

    def generate(self, op):
        self.op = op

        class_object = self._generate_class()
        ticket_object = self._generate_object(op, class_id=class_object["id"])

        self.put_item_cached(
            GoogleWalletType.CLASS, ClassType.eventTicketClass, class_object
        )
        self.put_item_cached(
            GoogleWalletType.OBJECT, ObjectType.eventTicketObject, ticket_object
        )

        generated_jwt = self.comms.sign_jwt(
            ButtonJWT(
                origins=[settings.SITE_URL],
                issuer=self.comms.client_email,
                event_ticket_objects=[ticket_object],
                skinny=True,
            )
        )

        return (
            "googlepaypass",
            "text/uri-list",
            "https://pay.google.com/gp/v/save/%s" % generated_jwt,
        )

    @property
    def settings(self):
        return [
            ImageSettingsField(
                identifier="logo",
                label=_("Logo"),
                default=self.event.settings.logo_image
                or "pretixplugins/wallet/logo.png",
            ),
            # TODO: wide logo
            ImageSettingsField(
                identifier="hero",
                label=_("Hero Image"),
            ),
            ColorSettingsField(
                identifier="bg_color",
                label=_("Background Color"),
                default=self.event.settings.primary_color,
            ),
            FloatSettingsField(identifier="lat", label=_("Latitude"), min=-90, max=90),
            FloatSettingsField(
                identifier="long", label=_("Longitude"), min=-180, max=180
            ),
            BooleanSettingsField(
                identifier="shimmer", label=_("Add shimmer animation around barcode")
            ),
        ]

    @property
    def fieldgroups(self) -> list[FieldGroup]:
        return [
            PredefinedFieldGroup(identifier="venue", name=_("Venue")),
            TextFieldGroup(
                identifier="code",
                name=_("QR-Code"),
                max_entries=1,
                display=FieldGroupDisplay.CODE,
                default_entries=[
                    PlaceholderFieldEntry(
                        content="secret",
                    )
                ],
                context_args={"order_position"},
            ),
        ]

    @property
    def preview_layout(self):
        return [
            {
                "style": {
                    "--background-color": {"setting": "bg_color"},
                    "color": "contrast-color(var(--background-color))",
                },
                "rows": [
                    {
                        "children": [
                            {"setting": "logo", "display": ["img-circle-sm"]},
                            {
                                "value": str(self.event.organizer.name),
                                "relSize": 3,
                                "display": ["large", "centered"],
                            },
                        ]
                    },
                    {
                        "children": [
                            {
                                "fieldgroup": "venue",
                                "sample": [
                                    {"content": self.venue()[0], "label": ""},
                                ],
                            },
                            {"value": str(self.event.name), "display": "large"},
                        ],
                        "direction": "column",
                        "display": ["tight"],
                    },
                    *self._preview_layout_front_card,
                    {"fieldgroup": "code"},
                    {"setting": "hero"},
                ],
            },
            {"rows": [*self._preview_layout_back_details]},
        ]

    @property
    def _preview_layout_front_card(self):
        return []

    @property
    def _preview_layout_back_details(self):
        return []

    def venue(self):
        if self.event.location:
            name = {}
            address = {}

            for key, value in self.event.location.data.items():
                lines = value.splitlines()
                name[key] = lines[0]
                # We must provide at least one address line each for the name and address - no way around it.
                if len(lines) > 1:
                    address[key] = "\n".join(value.splitlines()[1:])
                else:
                    address[key] = lines[0]

            return name, address
        return "", ""

    def _generate_class(self):
        output_class = EventTicketClass(
            self.event.organizer.name,
            get_class_id(self.event, self.op),
            MultipleDevicesAndHoldersAllowedStatus.multipleHolders,  # TODO: Make configurable
            self.event.name,
            ReviewStatus.underReview,
            self.event.settings.locale,
        )

        output_class.homepage_uri(
            eventreverse_absolute(self.event, "presale:event.index"),
            get_translated_string("Website", self.event.settings.locale),
            localizable_to_dict("Website", self.event.settings.locales),
        )

        if (lat := self.cleaned_settings["lat"]) and (
            long := self.cleaned_settings["long"]
        ):
            output_class.locations(lat, long)
        elif self.event.geo_lat and self.event.geo_lon:
            output_class.locations(self.event.geo_lat, self.event.geo_lon)

        output_class.country_code(self.event.settings.locale)

        if hero := self.cleaned_settings["hero"]:
            output_class.hero_image(
                urljoin(eventreverse_absolute(self.event, "presale:event.index"), hero),
                self.event.name,
            )

        if logo := self.cleaned_settings["logo"]:
            output_class.logo(
                urljoin(eventreverse_absolute(self.event, "presale:event.index"), logo),
                self.event.name,
            )

        output_class.hex_background_color(self.cleaned_settings["bg_color"])
        output_class.confirmation_code_label(ConfirmationCode.orderNumber)

        if self.group_is_active("venue") and all(self.venue()):
            output_class.venue(*self.venue())

        if self.cleaned_settings.get("shimmer", False):
            output_class.securityAnimation(AnimationType.FOIL_SHIMMER)

        # TODO: callback url
        # output_class.callback_url(eventreverse_absolute(event.organizer,"plugins:wallet:google_webhook",))

        return output_class

    def _generate_object(self, op: OrderPosition, class_id: str):
        output_object = EventTicketObject(
            get_object_id(op), class_id, ObjectState.active, self.event.settings.locale
        )
        fields = self.get_pass_fields(op)

        if fields["code"]:
            output_object.barcode(
                Barcode.qrCode, fields["code"][0]["value"], fields["code"][0]["value"]
            )
        output_object.reservation_info(op.order.code)
        output_object.ticket_number(op.code)

        output_object.valid_time_interval(op.valid_from, op.valid_until)
        output_object.ticket_type(
            get_translated_dict(
                str(op.item)
                + (" – " + str(op.variation.value) if op.variation else ""),
                op.order.event.settings.get("locales"),
            )
        )
        return output_object


class GoogleWalletDefaultEventTicket(GoogleWalletEventTicketStyle):
    identifier = "event"
    name = "Default Event Ticket"

    @property
    def fieldgroups(self):
        return [
            PredefinedFieldGroup(identifier="date", name=_("Date")),
            PredefinedFieldGroup(identifier="seating", name=_("Seating")),
            PredefinedFieldGroup(identifier="ticket_holder", name=_("Ticket Holder")),
            *super().fieldgroups,
        ]

    @property
    def _preview_layout_front_card(self):
        return [
            {
                "fieldgroup": "date",
                "sample": [
                    {
                        "content": date_format(
                            self.event.date_from.astimezone(self.event.timezone),
                            "SHORT_DATE_FORMAT",
                        ),
                        "label": "Date",
                    },
                    {
                        "content": date_format(
                            self.event.date_from.astimezone(self.event.timezone),
                            "TIME_FORMAT",
                        ),
                        "label": "Time",
                    },
                ],
            },
            {
                "fieldgroup": "seating",
                "sample": [
                    {"content": _("Ground floor"), "label": _("Section")},
                    {"content": "5 / 2", "label": _("Row") + " / " + _("Seat")},
                ],
            },
        ]

    @property
    def _preview_layout_back_details(self):
        return [
            {
                "fieldgroup": "ticket_holder",
                "sample": [
                    {"content": _("John Doe"), "label": _("Ticket Holder")},
                ],
            },
            {
                "fieldgroup": "venue",
                "sample": [
                    {"content": self.venue()[1], "label": self.venue()[0]},
                ],
            },
            {
                "fieldgroup": "date",
                "sample": [
                    {
                        "content": date_format(
                            self.event.date_from.astimezone(self.event.timezone),
                            "DATETIME_FORMAT",
                        ),
                        "label": _("Event Start Time"),
                    },
                ],
            },
            {"value": _("Sample product"), "label": _("Ticket Type")},
            {"value": "ABCDE-1", "label": _("Ticket Number")},
            {"value": "ABCDE", "label": _("Order Number")},
            {
                "value": eventreverse_absolute(self.event, "presale:event.index"),
                "label": _("Website"),
            },
        ]

    def _generate_class(self):
        output_class = super()._generate_class()
        if self.group_is_active("date"):
            if self.event.date_from:
                output_class.start(self.event.date_from.isoformat())

            if self.event.settings.show_date_to and self.event.date_to:
                output_class.end(self.event.date_to.isoformat())

            if self.event.date_admission:
                output_class.doors_open(
                    DoorsOpen.doorsOpen, self.event.date_admission.isoformat()
                )

        return output_class

    def ticket_holder_name(self, op):
        return op.attendee_name or (op.addon_to.attendee_name if op.addon_to else None)

    def _generate_object(self, op: OrderPosition, class_id: str):
        output_object = super()._generate_object(op, class_id)

        if self.group_is_active("ticket_holder") and self.ticket_holder_name(op):
            output_object.ticket_holder_name(self.ticket_holder_name(op))

        if self.group_is_active("seating") and (seat := self.op.seat):
            if seat.zone_name:
                output_object.section(seat.zone_name)

            if seat.row_label:
                output_object.row(seat.row_label)
            elif seat.row_name:
                output_object.row(seat.row_name)

            if seat.seat_label:
                output_object.seat(seat.seat_label)
            elif seat.seat_number:
                output_object.seat(seat.seat_number)

        # places = settings.CURRENCY_PLACES.get(op.order.event.currency, 2)
        # output_object.face_value(int(op.price * 1000 ** places), op.order.event.currency)

        return output_object


class GoogleWalletCustomEventTicket(GoogleWalletEventTicketStyle):
    identifier = "event_custom"
    name = "Custom Event Ticket"

    @property
    def _preview_layout_front_card(self):
        return [
            {
                "fieldgroup": "second_row",
            },
            {
                "fieldgroup": "third_row",
            },
        ]

    @property
    def _preview_layout_back_details(self):
        return [{"fieldgroup": "details", "direction": "column"}]

    @property
    def fieldgroups(self):
        return [
            *super().fieldgroups,
            TextFieldGroup(
                identifier="second_row",
                name=_("Second Row"),
                max_entries=3,
                context_args={"order_position"},
            ),
            TextFieldGroup(
                identifier="third_row",
                name=_("Third Row"),
                max_entries=3,
                context_args={"order_position"},
            ),
            TextFieldGroup(
                identifier="details",
                name=_("Details"),
                context_args={"order_position"},
            ),
        ]

    def _generate_class(self):
        output_class = super()._generate_class()

        output_class.setdefault("classTemplateInfo", {})
        output_class["classTemplateInfo"].setdefault("cardTemplateOverride", {})
        output_class["classTemplateInfo"]["cardTemplateOverride"] = {
            "cardRowTemplateInfos": [
                {
                    "threeItems": {
                        "startItem": {
                            "firstValue": {
                                "fields": [
                                    {
                                        "fieldPath": "object.textModulesData['second_row-0']"
                                    }
                                ]
                            }
                        },
                        "middleItem": {
                            "firstValue": {
                                "fields": [
                                    {
                                        "fieldPath": "object.textModulesData['second_row-1']"
                                    }
                                ]
                            }
                        },
                        "endItem": {
                            "firstValue": {
                                "fields": [
                                    {
                                        "fieldPath": "object.textModulesData['second_row-2']"
                                    }
                                ]
                            }
                        },
                    }
                },
                {
                    "threeItems": {
                        "startItem": {
                            "firstValue": {
                                "fields": [
                                    {
                                        "fieldPath": "object.textModulesData['third_row-0']"
                                    }
                                ]
                            }
                        },
                        "middleItem": {
                            "firstValue": {
                                "fields": [
                                    {
                                        "fieldPath": "object.textModulesData['third_row-1']"
                                    }
                                ]
                            }
                        },
                        "endItem": {
                            "firstValue": {
                                "fields": [
                                    {
                                        "fieldPath": "object.textModulesData['third_row-2']"
                                    }
                                ]
                            }
                        },
                    }
                },
            ]
        }

        output_class["classTemplateInfo"].setdefault("detailsTemplateOverride", {})
        output_class["classTemplateInfo"]["detailsTemplateOverride"][
            "detailsItemInfos"
        ] = [
            {
                "item": {
                    "firstValue": {
                        "fields": [
                            {"fieldPath": f"object.textModulesData['details-{i}']"}
                        ]
                    }
                }
            }
            for i in range(
                len(self.layout["fieldgroups"].get("details", {}).get("entries", []))
            )
        ]
        return output_class

    def _generate_object(self, op: OrderPosition, class_id: str):
        output_object = super()._generate_object(op, class_id)
        fields = self.get_pass_fields(op)

        for row in ["second_row", "third_row", "details"]:
            for i, field in enumerate(fields.get(row, [])):
                output_object.text_modules_data(
                    f"{row}-{i}",
                    localizable_to_dict(field["label"], self.event.settings.locales),
                    localizable_to_dict(field["value"], self.event.settings.locales),
                )

        return output_object
