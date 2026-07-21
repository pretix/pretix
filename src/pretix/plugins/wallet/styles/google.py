from pretix.base.models import Event, OrderPosition

from .base import (
    FieldGroupDisplay,
    ImageFieldGroup,
    PassLayout,
    PassStyle,
    PlaceholderFieldEntry,
    PredefinedFieldGroup,
    TextFieldGroup,
    WalletPlatform,
)
from django.utils.translation import gettext_lazy as _, gettext
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

    return "%s.pretix-%s-%s-%s-%s-%s" % (
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
        translated[locale] = gettext(string)
        translation.deactivate()

    return translated


def get_translated_string(string, locale):
    translation.activate(locale)
    translated = gettext(string)
    translation.deactivate()

    return translated


class GooglePlatform(WalletPlatform):
    identifier = "google"
    name = _("Google")

    @classmethod
    def generate(cls, layout: PassLayout, op: OrderPosition):
        from ..views import get_layout_variables

        order = op.order
        event = order.event

        context = {
            "placeholders": get_layout_variables(event),  # TODO: move to higher class
            "evaluation_context": [op, order, event],
            "credentials": event.settings.get("wallet_google_credentials").read(),
            "locale": event.settings.locale,
            "locales": event.settings.locales,
            "issuerName": event.organizer.name,
            "eventName": event.name,
            "classId": get_class_id(event),
            "objectId": get_object_id(op),
            "homepageUrl": eventreverse_absolute(event, "presale:event.index"),
            # TODO: add webhook view & register in pass
            "webhookUrl": "",  # eventreverse_absolute(event.organizer,"plugins:wallet:google_webhook",))
        }

        data = layout.generate(context)
        return "pass", "text/plain", data


class GoogleWalletStyle(PassStyle):
    platform = GooglePlatform

    @classmethod
    def _comms(cls, event: Event):
        return Comms()

    def _generate_class(self, layout, context, fields):
        raise NotImplementedError()

    def _generate_object(self, layout, context, fields):
        raise NotImplementedError()

    def generate(self, layout, context):
        comms = Comms(context["credentials"])
        fields = self.get_pass_fields(layout, context)

        class_object = self._generate_class(layout, context, fields)
        ticket_object = self._generate_object(layout, context, fields)

        generated_jwt = comms.sign_jwt(
            ButtonJWT(
                origins=[settings.SITE_URL],
                issuer=comms.client_email,
                event_ticket_classes=[class_object],
                event_ticket_objects=[ticket_object],
                skinny=False,
            )
        )

        return "https://pay.google.com/gp/v/save/%s" % generated_jwt

        # from ..views import get_layout_variables

        # order = op.order
        # event = order.event
        # filename = "{}-{}.pkpass".format(order.event.slug, order.code)

        # ticket = str(op.item.name)
        # if op.variation:
        #     ticket += " - " + str(op.variation)

        # serialNumber = "%s-%s-%s-%d" % (
        #     order.event.organizer.slug,
        #     order.event.slug,
        #     order.code,
        #     op.pk,
        # )

        # context = {
        #     "placeholders": get_layout_variables(op.order.event),
        #     "evaluation_context": [op, order, order.event],
        #     "ca_certificate": order.event.settings.wallet_apple_ca_certificate.read(),
        #     "certificate": order.event.settings.wallet_apple_certificate.read(),
        #     "key": order.event.settings.wallet_apple_key.read(),
        #     "password": order.event.settings.wallet_apple_key_password,
        #     "description": _("Ticket for {event} ({product})").format(  # TODO: i18n
        #         event=event.name, product=ticket
        #     ),
        #     "organizationName": event.organizer.name,
        #     "passTypeIdentifier": order.event.settings.wallet_apple_pass_type_id,
        #     "teamIdentifier": order.event.settings.wallet_apple_team_id,
        #     "serialNumber": serialNumber,
        #     "locales": event.settings.locales,
        # }

        # data = layout.generate(context)
        # return filename, "application/vnd.apple.pkpass", data


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
            {"fieldgroup": "seating"},
            {"fieldgroup": "code"},
        ]
    ]

    def _generate_class(self, layout: PassLayout, context, fields):
        output_class = EventTicketClass(
            context["issuerName"],
            context["classId"],
            MultipleDevicesAndHoldersAllowedStatus.multipleHolders,  # TODO: Make configurable
            context["eventName"],
            ReviewStatus.underReview,
            context["locale"],
        )

        output_class.homepage_uri(
            context["homepageUrl"],
            get_translated_string("Website", context["locale"]),
            get_translated_dict("Website", context["locales"]),
        )
        # TODO: add webhook view & register in pass
        # output_class.callback_url(context['webhookUrl'])

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
        return output_class._eventTicketClass

    def _generate_object(self, layout: PassLayout, context, fields):
        class_id = context["classId"]
        object_id = context["objectId"]
        output_object = EventTicketObject(
            object_id, class_id, ObjectState.active, context["locale"]
        )

        # output_object.barcode(Barcode.qrCode, op.secret, op.secret)

        # output_object.reservation_info("%s-%s" % (op.order.event.slug, op.order.code))
        # output_object.ticket_holder_name(op.attendee_name or (op.addon_to.attendee_name if op.addon_to else ''))
        # output_object.ticket_number(op.secret)
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
        return output_object._eventTicketObject
