from urllib.parse import urljoin

from django.utils.translation import gettext as _

from pretix.base.models import OrderPosition
from pretix.multidomain.urlreverse import eventreverse_absolute
from pretix.plugins.wallet.i18n import (
    FormattingLocalizableString, GettextLocalizableString, LazyLocalizable,
)

from ..base import (
    FieldGroup, FieldGroupDisplay, PassStyle, PlaceholderFieldEntry,
    PredefinedFieldGroup, TextFieldGroup,
)

from .google_wallet import (
    AnimationType, ConfirmationCodeLabel, DoorsOpenLabel, EventTicketClass, EventTicketObject,
    State,
)

from ..settings import (
    BooleanSettingsField, ColorSettingsField, FloatSettingsField,
    ImageSettingsField,
)
from .platform import get_class_id, get_object_id

class GoogleWalletEventTicketStyle(PassStyle):
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
