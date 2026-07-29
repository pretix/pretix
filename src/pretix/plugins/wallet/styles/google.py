from pretix.base.models import Event, OrderPosition

from .base import (
    FieldGroupDisplay,
    ImageFieldGroup,
    PassStyle,
    PlaceholderFieldEntry,
    PredefinedFieldGroup,
    TextFieldGroup,
    WalletPlatform,
)
from django.utils.translation import gettext as _
import json

from walletobjects import ButtonJWT, EventTicketClass, EventTicketObject
from walletobjects.comms import Comms
from walletobjects.constants import (
    Barcode,
    ClassType,
    ConfirmationCode,
    DoorsOpen,
    MultipleDevicesAndHoldersAllowedStatus,
    ObjectState,
    ObjectType,
    ReviewStatus,
    Seat,
)
from pretix.base.settings import GlobalSettingsObject
import uuid
from pretix.multidomain.urlreverse import eventreverse_absolute
from django.utils import translation
from django.conf import settings


def _get_instance_uuid():
    gs = GlobalSettingsObject()
    if not gs.settings.wallet_google_instance_uuid:
        gs.settings.wallet_google_instance_uuid = str(uuid.uuid4())

    return gs.settings.wallet_google_instance_uuid


def get_class_id(event: Event):
    # TODO: add layout id somewhere
    instance_uuid = _get_instance_uuid()
    issuer_id = event.settings.get("wallet_google_issuer_id")
    return "%s.pretix-%s-%s-%s" % (
        issuer_id,
        instance_uuid,
        event.organizer.slug,
        event.slug,
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


class GoogleWalletStyle(PassStyle):
    platform = GooglePlatform

    def _generate_class(self):
        output_class = EventTicketClass(
            self.event.organizer.name,
            get_class_id(self.event),
            MultipleDevicesAndHoldersAllowedStatus.multipleHolders,  # TODO: Make configurable
            self.event.name,
            ReviewStatus.underReview,
            self.event.settings.locale,
        )

        output_class.homepage_uri(
            eventreverse_absolute(self.event, "presale:event.index"),
            get_translated_string("Website", self.event.settings.locale),
            get_translated_dict("Website", self.event.settings.locales),
        )

        # TODO: callback url
        # output_class.callback_url(eventreverse_absolute(event.organizer,"plugins:wallet:google_webhook",))

        # TODO: move to pass settings or set defaults
        # if (event.settings.get('ticketoutput_googlepaypasses_latitude')
        #         and event.settings.get('ticketoutput_googlepaypasses_longitude')):
        #     output_class.locations(
        #         event.settings.get('ticketoutput_googlepaypasses_latitude'),
        #         event.settings.get('ticketoutput_googlepaypasses_longitude')
        #     )
        # elif event.geo_lat and event.geo_lon:
        #     output_class.locations(
        #         event.geo_lat,
        #         event.geo_lon
        #     )

        # output_class.country_code(event.settings.locale)

        # if event.settings.get('ticketoutput_googlepaypasses_hero'):
        #     output_class.hero_image(
        #         urljoin(django_settings.SITE_URL, event.settings.get('ticketoutput_googlepaypasses_hero').url),
        #         str(event.name),
        #         event.name,
        #     )

        # output_class.hex_background_color(event.settings.get('primary_color'))
        # output_class.event_id('pretix-%s-%s-%s' % (gs.settings.get('update_check_id'), event.organizer.id, event.id))

        # if event.settings.get('ticketoutput_googlepaypasses_logo'):
        #     output_class.logo(
        #         urljoin(django_settings.SITE_URL, event.settings.get('ticketoutput_googlepaypasses_logo').url),
        #         str(event.name),
        #         event.name,
        #     )

        # if event.location:
        #     name = {}
        #     address = {}

        #     for key, value in event.location.data.items():
        #         lines = value.splitlines()
        #         name[key] = lines[0]
        #         # We must provide at least one address line each for the name and address - no way around it.
        #         if len(lines) > 1:
        #             address[key] = '\n'.join(value.splitlines()[1:])
        #         else:
        #             address[key] = lines[0]

        #     output_class.venue(name, address)

        # if event.date_from and event.date_to and event.date_admission:
        #     output_class.date_time(
        #         DoorsOpen.doorsOpen,
        #         event.date_admission.isoformat(),
        #         event.date_from.isoformat(),
        #         event.date_to.isoformat(),
        #     )

        # output_class.confirmation_code_label(ConfirmationCode.orderNumber)

        # if event.seating_plan_id is not None:
        #     output_class.seat_label(Seat.seat)

        # return self._comms().put_item(ClassType.eventTicketClass, class_name, output_class)
        return output_class

    def _generate_object(self, op: OrderPosition, class_id: str):
        output_object = EventTicketObject(
            get_object_id(op), class_id, ObjectState.active, self.event.settings.locale
        )
        return output_object

    def generate(self, op):
        self.op = op
        comms = Comms(self.event.settings.get("wallet_google_credentials").read())

        class_object = self._generate_class()
        ticket_object = self._generate_object(op, class_id=class_object['id'])

        # TODO: privacy screen
        class_object = comms.put_item(ClassType.eventTicketClass, class_object['id'], class_object)
        ticket_object = comms.put_item(ObjectType.eventTicketObject, ticket_object['id'], ticket_object)

        generated_jwt = comms.sign_jwt(
            ButtonJWT(
                origins=[settings.SITE_URL],
                issuer=comms.client_email,
                event_ticket_objects=[ticket_object],
                skinny=True,
            )
        )

        return "https://pay.google.com/gp/v/save/%s" % generated_jwt


class GoogleWalletEventTicket(GoogleWalletStyle):
    identifier = "event"
    name = "Event Ticket"
    fieldgroups = [
        ImageFieldGroup(
            identifier="logo",
            name=_("Logo"),
            min_entries=0,
            max_entries=1,
            default_entries=[
                PlaceholderFieldEntry(
                    content="poweredby",
                )
            ],
        ),
        PredefinedFieldGroup(identifier="seating", name=_("Seating")),
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
        ),
    ]
    preview_layout = [
        [
            {
                "children": [
                    {"fieldgroup": "logo", "relSize": 1},
                    {
                        "value": "issuerName",
                        "relSize": 3,
                        "display": ["large", "centered"],
                    },
                ]
            },
            {
                "children": [
                    {"value": "venueName", "display": "small"},
                    {"value": "eventName", "display": "large"},
                ],
                "direction": "column",
            },
            {
                "children": [
                    {"value": "01/01/1970", "label": "Date"},
                    {"value": "12:34", "label": "Time"},
                ]
            },
            {"fieldgroup": "seating",
             "sample": [
                    {"content": "5", "label": "Row"},
                    {"content": "2", "label": "Seat"},
                ]
            },
            {"fieldgroup": "code"},
        ]
    ]

    def _generate_object(self, op: OrderPosition, class_id: str):
        output_object = super()._generate_object(op, class_id)

        if fields["code"]:
            output_object.barcode(
                Barcode.qrCode, fields["code"][0]["value"], fields["code"][0]["value"]
            )

        # output_object.reservation_info("%s-%s" % (op.order.event.slug, op.order.code))
        # output_object.ticket_holder_name(op.attendee_name or (op.addon_to.attendee_name if op.addon_to else ''))
        output_object.ticket_holder_name("Some name")
        output_object.ticket_number(fields["code"][0]["value"])
        # output_object.ticket_type(
        #     get_translated_dict(
        #         str(op.item) + (" – " + str(op.variation.value) if op.variation else ""),
        #         op.order.event.settings.get('locales')
        #     )
        # )

        # places = django_settings.CURRENCY_PLACES.get(op.order.event.currency, 2)
        # output_object.face_value(int(op.price * 1000 ** places), op.order.event.currency)

        # if op.order.event.seating_plan_id is not None:
        #     if op.seat:
        #         output_object.seat(
        #             get_translated_dict(
        #                 _(str(op.seat)),
        #                 op.order.event.settings.get('locales')
        #             )
        #         )
        #     else:
        #         output_object.seat(
        #             get_translated_dict(
        #                 _('General admission'),
        #                 op.order.event.settings.get('locales')
        #             )
        #         )

        # return self._comms().put_item(ObjectType.eventTicketObject, object_name, output_object)
        return output_object
