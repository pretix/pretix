import json
import uuid
from functools import cached_property
from typing import Iterable
from urllib.parse import urljoin

from django.conf import settings
from django.db import transaction
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from pretix.base.models import Event, OrderPosition
from pretix.base.settings import GlobalSettingsObject
from pretix.multidomain.urlreverse import eventreverse_absolute
from pretix.plugins.wallet.i18n import (
    FormattingLocalizableString, GettextLocalizableString, LazyLocalizable,
)
from pretix.plugins.wallet.models import GoogleWalletInstance
from pretix.plugins.wallet.styles.base import (
    FieldGroup, FieldGroupDisplay, PassStyle, PlaceholderFieldEntry,
    PredefinedFieldGroup, TextFieldGroup, WalletPlatform,
)

from .google_wallet import (
    AnimationType, BaseGoogleWalletObject, ButtonJWT, Comms,
    ConfirmationCodeLabel, DoorsOpenLabel, EventTicketClass, EventTicketObject,
    State,
)
from .settings import (
    BooleanSettingsField, ColorSettingsField, FloatSettingsField,
    ImageSettingsField,
)


def _get_instance_uuid():
    gs = GlobalSettingsObject()
    if not gs.settings.wallet_google_instance_uuid:
        gs.settings.wallet_google_instance_uuid = str(uuid.uuid4())

    return gs.settings.wallet_google_instance_uuid


def get_class_id(event: Event, op: OrderPosition):
    instance_uuid = _get_instance_uuid()
    issuer_id = event.settings.wallet_google_issuer_id
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
    issuer_id = op.order.event.settings.wallet_google_issuer_id

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


def dedup(list):
    new = []
    for i in list:
        if not any(x.data == i.data for x in new):
            new.append(i)
    return new


class GooglePlatform(WalletPlatform):
    identifier = "google"
    name = _("Google")

    @cached_property
    def comms(self):
        return Comms(
            json.loads(self.event.settings.get("wallet_google_credentials").read())
        )

    def put_item_cached(self, object: BaseGoogleWalletObject):
        with transaction.atomic():
            instance, created = GoogleWalletInstance.objects.get_or_create(
                event=self.event,
                resource=object.resource,
                identifier=object.id,
                defaults={"data": object.data},
            )
            if created or instance.data != object.data:
                result = self.comms.put_item(object.resource, object.id, object.data)
                instance.data = object.data
                instance.save(update_fields=["data"])
                return result

    def generate(self, position, layout: PassStyle | None = None):
        if not layout:
            layout = self.get_layout(position).pass_layout
        class_object, ticket_object = layout.generate(position)
        self.put_item_cached(class_object)
        self.put_item_cached(ticket_object)

        generated_jwt = self.comms.sign_jwt(
            ButtonJWT(
                origins=[settings.SITE_URL],
                issuer=self.comms.client_email,
                payload={"eventTicketObjects": [ticket_object]},
            ).serialize()
        )

        return (
            "googlepaypass",
            "text/uri-list",
            "https://pay.google.com/gp/v/save/%s" % generated_jwt,
        )

    def generate_ops(self, ops: Iterable[OrderPosition]):
        class_objects = []
        ticket_objects = []
        for position in ops:
            class_object, ticket_object = self.get_layout(
                position
            ).pass_layout.generate(position)
            class_objects.append(class_object)
            ticket_objects.append(ticket_object)

        for co in dedup(class_objects):
            self.put_item_cached(co)
        for to in dedup(ticket_objects):
            self.put_item_cached(to)

        generated_jwt = self.comms.sign_jwt(
            ButtonJWT(
                origins=[settings.SITE_URL],
                issuer=self.comms.client_email,
                payload={"eventTicketObjects": ticket_objects},
            ).serialize()
        )

        return (
            "googlepaypass",
            "text/uri-list",
            "https://pay.google.com/gp/v/save/%s" % generated_jwt,
        )


class GoogleWalletEventTicketStyle(PassStyle):
    platform = GooglePlatform

    def generate(self, op):
        self.op = op

        class_object = self._generate_class()
        ticket_object = self._generate_object(op, class_id=class_object.id)

        return class_object, ticket_object

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
            FloatSettingsField(
                identifier="lat",
                label=_("Latitude"),
                min=-90,
                max=90,
                default=self.event.geo_lat,
            ),
            FloatSettingsField(
                identifier="long",
                label=_("Longitude"),
                min=-180,
                max=180,
                default=self.event.geo_lon,
            ),
            BooleanSettingsField(
                identifier="shimmer", label=_("Add shimmer animation around barcode")
            ),
        ]

    @property
    def fieldgroups(self) -> list[FieldGroup]:
        return [
            PredefinedFieldGroup(identifier="venue", name=_("Venue")),
            PredefinedFieldGroup(identifier="date", name=_("Date")),
            TextFieldGroup(
                identifier="code",
                name=_("QR-Code"),
                max_entries=1,
                display=FieldGroupDisplay.PLAIN,
                default_entries=[
                    PlaceholderFieldEntry(
                        content="secret",
                    )
                ],
                context_args={"order_position"},
            ),
        ]

    @property
    def preview_data(self):
        return {
            "event": str(self.event),
            "organizer": str(self.event.organizer),
            "date_from": self.event.date_from.astimezone(
                self.event.timezone
            ).isoformat(),
            "venue": self.venue(),
            "event_page": eventreverse_absolute(self.event, "presale:event.index"),
        }

    def venue(self):
        if not str(self.event.location).strip():
            return

        def _get_name():
            lines = str(self.event.location).strip().splitlines()
            return lines[0]

        def _get_address():
            lines = str(self.event.location).splitlines()
            # We must provide at least one address line each for the name and address - no way around it.
            if len(lines) > 1:
                return "\n".join(lines[1:])
            else:
                return lines[0]

        return LazyLocalizable(_get_name), LazyLocalizable(_get_address)

    def _generate_class(self):
        output_class = EventTicketClass(
            self.event.organizer.name,
            get_class_id(self.event, self.op),
            self.event.name,
            self.event.settings.locales,
            self.event.settings.locale,
        )

        output_class.homepage_uri(
            eventreverse_absolute(self.event, "presale:event.index"),
            GettextLocalizableString.gettext("Website"),
        )

        # TODO: merchantLocations, locations is deprecated
        # if (lat := self.get_cleaned_setting("lat")) and (
        #     long := self.get_cleaned_setting("long")
        # ):
        #     output_class.locations(lat, long)
        output_class.country_code(self.event.settings.locale)

        if hero := self.get_cleaned_setting("hero"):
            output_class.hero_image(
                urljoin(
                    eventreverse_absolute(self.event, "presale:event.index"), hero.url
                ),
                self.event.name,
            )

        if logo := self.get_cleaned_setting("logo"):
            output_class.logo(
                urljoin(
                    eventreverse_absolute(self.event, "presale:event.index"), logo.url
                ),
                self.event.name,
            )

        output_class.hex_background_color(self.get_cleaned_setting("bg_color"))
        output_class.confirmation_code_label(ConfirmationCodeLabel.ORDER_NUMBER)

        if self.group_is_active("venue") and (venue := self.venue()):
            output_class.venue(*venue)

        if self.get_cleaned_setting("shimmer"):
            output_class.security_animation(AnimationType.FOIL_SHIMMER)

        if self.group_is_active("date"):
            output_class.start(
                self.event.date_from.astimezone(self.event.timezone).isoformat()
            )

            if self.event.settings.show_date_to and self.event.date_to:
                output_class.end(
                    self.event.date_to.astimezone(self.event.timezone).isoformat()
                )

            if self.event.date_admission:
                output_class.doors_open(
                    self.event.date_admission.astimezone(
                        self.event.timezone
                    ).isoformat(),
                    DoorsOpenLabel.DOORS_OPEN,
                )

        output_class.callback_url(
            eventreverse_absolute(
                self.event,
                "plugins:wallet:google_webhook",
            )
        )

        return output_class

    def _generate_object(self, op: OrderPosition, class_id: str):
        output_object = EventTicketObject(
            get_object_id(op),
            class_id,
            State.ACTIVE,
            self.event.settings.locales,
            self.event.settings.locale,
        )
        fields = self.get_pass_fields(op)

        if fields["code"]:
            output_object.barcode(fields["code"][0]["value"])

        output_object.reservation_info(op.order.code)
        output_object.ticket_number(op.code)

        output_object.valid_time_interval(op.valid_from, op.valid_until)
        output_object.ticket_type(
            FormattingLocalizableString(
                "{name} - {variation}", name=op.item.name, variation=op.variation.value
            )
            if op.variation
            else op.item.name
        )

        return output_object


class GoogleWalletDefaultEventTicket(GoogleWalletEventTicketStyle):
    identifier = "event"
    name = "Default Event Ticket"

    @property
    def preview_renderer(self):
        return "google_eventticket_default"

    @property
    def fieldgroups(self):
        return [
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
        venue = self.venue()
        if not venue:
            venue = _("Sample Conference Center\nHeidelberg, Germany").split("\n", 1)
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
                    {"content": venue[1], "label": venue[0]},
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
            {"content": _("Sample product"), "label": _("Ticket Type")},
            {"content": "ABCDE-1", "label": _("Ticket Number")},
            {"content": "ABCDE", "label": _("Order Number")},
            {
                "content": eventreverse_absolute(self.event, "presale:event.index"),
                "label": _("Website"),
            },
        ]

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

        return output_object


class GoogleWalletCustomEventTicket(GoogleWalletEventTicketStyle):
    identifier = "event_custom"
    name = "Custom Event Ticket"

    @property
    def preview_renderer(self):
        return "google_eventticket_custom"

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

        output_class.card_template_override(
            [
                [
                    "object.textModulesData['second_row-0']"
                    "object.textModulesData['second_row-1']"
                    "object.textModulesData['second_row-2']"
                ],
                [
                    "object.textModulesData['third_row-0']",
                    "object.textModulesData['third_row-1']",
                    "object.textModulesData['third_row-2']",
                ],
            ]
        )

        output_class.details_item_infos(
            [
                f"object.textModulesData['details-{i}']"
                for i in range(
                    len(
                        self.layout["fieldgroups"].get("details", {}).get("entries", [])
                    )
                )
            ]
        )
        return output_class

    def _generate_object(self, op: OrderPosition, class_id: str):
        output_object = super()._generate_object(op, class_id)
        fields = self.get_pass_fields(op)

        for row in ["second_row", "third_row", "details"]:
            for i, field in enumerate(fields.get(row, [])):
                output_object.add_text_module(
                    f"{row}-{i}",
                    field["label"],
                    field["value"],
                )

        return output_object
