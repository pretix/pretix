from pretix.base.models import Event, OrderPosition

from .base import FieldGroupDisplay, PassLayout, PassStyle, PredefinedFieldGroup, TextFieldGroup, WalletPlatform
from django.utils.translation import gettext_lazy as _, gettext
import json

from walletobjects import ButtonJWT, EventTicketClass, EventTicketObject
from walletobjects.comms import Comms
from walletobjects.constants import (
    Barcode, ClassType, ConfirmationCode, DoorsOpen,
    MultipleDevicesAndHoldersAllowedStatus, ObjectState, ObjectType,
    ReviewStatus, Seat,
)
from pretix.base.settings import GlobalSettingsObject
import uuid
from pretix.multidomain.urlreverse import eventreverse_absolute
from django.utils import translation

def _get_instance_uuid():
    gs = GlobalSettingsObject()
    if not gs.settings.wallet_google_instance_uuid:
        gs.settings.wallet_google_instance_uuid = str(uuid.uuid4())
    return gs.settings.get("wallet_google_instance_uuid")

def get_class_id(event: Event):
    instance_uuid = _get_instance_uuid()
    issuer_id = event.settings.get('wallet_google_issuer_id')
    return "%s.pretix-%s-%s-%s" % (issuer_id, instance_uuid, event.organizer.slug, event.slug)


def get_object_id(op: OrderPosition):
    instance_uuid = _get_instance_uuid()
    issuer_id = op.order.event.settings.get('wallet_google_issuer_id')

    return "%s.pretix-%s-%s-%s-%s-%s" % (issuer_id, instance_uuid,
                                            op.order.event.organizer.slug, op.order.event.slug,
                                            op.order.code, op.positionid)

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
        class_object = cls._generate_class(op.order.event)

        # ticket_object = cls._get_object(op)

        # if not ticket_object:
        #     return False

        # generated_jwt = self._comms().sign_jwt(
        #     ButtonJWT(
        #         origins=[django_settings.SITE_URL],
        #         issuer=self._comms().client_email,
        #         event_ticket_objects=[ticket_object],
        #         skinny=True
        #     )
        # )

        # if generated_jwt:
        #     return 'googlepaypass', 'text/uri-list', 'https://pay.google.com/gp/v/save/%s' % generated_jwt
        # else:
        #     return False

        data = {"class": class_object}
        return 'pass.json', 'application/json', json.dumps(data)
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

    @classmethod
    def _generate_class(cls, event: Event):
        class_name = get_class_id(event)

        output_class = EventTicketClass(
            event.organizer.name,
            class_name,
            MultipleDevicesAndHoldersAllowedStatus.multipleHolders,  # TODO: Make configurable
            event.name,
            ReviewStatus.draft, # TODO: ReviewStatus.underReview,
            event.settings.locale
        )

        output_class.homepage_uri(
            eventreverse_absolute(event, 'presale:event.index'),
            get_translated_string('Website', event.settings.locale),
            get_translated_dict('Website', event.settings.locales)
        )

        # output_class.callback_url(eventreverse_absolute(event.organizer, 'plugins:pretix_googlepaypasses:webhook'))

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

        output_class.country_code(event.settings.locale)

        output_class.hide_barcode(False)

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


class GoogleWalletStyle(PassStyle):
    platform = GooglePlatform


class GoogleWalletEventTicket(PassStyle):
    identifier = "event"
    name = "Event Ticket"
    platform = GooglePlatform
    fieldgroups = [
        PredefinedFieldGroup(identifier="seating", name=_("Seating")),
        TextFieldGroup(identifier="qrcode", name=_("QR-Code"), display=FieldGroupDisplay.PLAIN),
    ]
    preview_layout = None