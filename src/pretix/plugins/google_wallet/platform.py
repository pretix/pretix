import base64
import json
import uuid
from functools import cached_property

from django.conf import settings
from django.db import transaction
from django.utils.crypto import salted_hmac
from django.utils.functional import classproperty
from django.utils.html import format_html
from django.utils.translation import gettext as _

from pretix.base.models import Event, OrderPosition
from pretix.base.models.orders import Order
from pretix.base.settings import GlobalSettingsObject
from pretix.base.wallet.platforms import (
    PassStyle, WalletPlatform, wallet_platform_registry,
)

from .google_wallet import BaseGoogleWalletObject, ButtonJWT, Comms
from .models import GoogleWalletInstance


def _get_instance_uuid():
    gs = GlobalSettingsObject()
    if not gs.settings.update_check_id:
        gs.settings.set('update_check_id', uuid.uuid4().hex)

    return gs.settings.update_check_id


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
    issuer_id = op.order.event.settings.wallet_google_issuer_id
    event = op.order.event
    organizer = event.organizer

    op_secret = base64.urlsafe_b64encode(salted_hmac(
        key_salt="pretix.plugins.wallet.google.object_id",
        algorithm="sha256",
        secret=op.web_secret,
        value=str(op.pk),
    ).digest()).decode().rstrip("=")

    return f"{issuer_id}.pretix-{organizer.slug}-{event.slug}-{op_secret}"


def dedup(objects: list[BaseGoogleWalletObject]):
    new = []
    for i in objects:
        if not any(x.data == i.data for x in new):
            new.append(i)
    return new


@wallet_platform_registry.register
class GooglePlatform(WalletPlatform):
    identifier = "google"
    name = _("Google Wallet")

    def render_download_button(self) -> tuple[dict[str, str] | None, str]:
        confirmation_text = _(
            "Please be aware, that contrary to other virtual wallets/passes (like Apple Wallet), Google Wallet Passes are not "
            "handled offline. Every pass that is created, has to be transmitted to Google Inc.\n"
            "\n"
            'By clicking "Confirm" below, we will transfer some of your personal information, which is '
            "necessary to provide you with your Google Wallet Pass, to Google Inc.\n"
            "\n"
            "Please be aware, that there is no way to delete the data, once it has been transmitted.\n"
        )
        return (
            {"data-confirmation-text": confirmation_text},
            format_html(
                '<span class="fa fa-download"></span> {}',
                _("Add to {wallet}").format(wallet=self.name),
            ),
        )

    @classproperty
    def default_style(self):
        return "event"

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
                defaults={"data": object.data, "order_position": object.order_position},
            )
            if created or instance.data != object.data:
                result = self.comms.put_item(object.resource, object.id, object.data)
                instance.data = object.data
                instance.save(update_fields=["data"])
                return result

    def _get_jwt(self, ticket_objects):
        for to in dedup(ticket_objects):
            self.put_item_cached(to)
        generated_jwt = self.comms.sign_jwt(
            ButtonJWT(
                origins=[settings.SITE_URL],
                issuer=self.comms.client_email,
                payload={"eventTicketObjects": ticket_objects},
                precreated=False,
            ).serialize()
        )

        return f"https://pay.google.com/gp/v/save/{generated_jwt}"

    def generate(self, position):
        # TODO?: early-exit caching (if object for position exists)
        op_layout = self.get_layout(position)
        if not op_layout:
            raise ValueError(
                _(
                    "WalletPlatform.generate called without layout and without position layout"
                )
            )
        layout = op_layout.pass_layout

        class_object, ticket_object = layout.generate(position)
        self.put_item_cached(class_object)

        return self._get_jwt([ticket_object])

    def generate_preview(self, position: OrderPosition, layout: PassStyle) -> str:
        class_object, ticket_object = layout.generate(position)
        self.put_item_cached(class_object)

        return self._get_jwt([ticket_object])

    def generate_order(self, order: Order):
        class_objects = []
        ticket_objects = []
        for position in order.positions_with_tickets:
            if self.is_available_for_position(position):
                layout = self.get_layout(position)
                if not layout:
                    raise ValueError(
                        "Impossible: is_available_for_position==True but no layout"
                    )

                class_object, ticket_object = layout.pass_layout.generate(position)
                class_objects.append(class_object)
                ticket_objects.append(ticket_object)

        for co in dedup(class_objects):
            self.put_item_cached(co)

        return self._get_jwt(ticket_objects)

    def is_available(self):
        for field in ["wallet_google_issuer_id", "wallet_google_credentials"]:
            if not self.event.settings.get(field):
                return False
        return super().is_available()
