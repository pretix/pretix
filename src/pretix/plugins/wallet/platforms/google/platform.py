import json
import uuid
from functools import cached_property
from typing import Iterable, OrderedDict

from django.conf import settings
from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _
from django import forms

from pretix.base.models import Event, OrderPosition
from pretix.base.settings import GlobalSettingsObject
from pretix.plugins.wallet.models import GoogleWalletInstance
from ..base import (
    PassStyle,
    WalletPlatform,
)

from .google_wallet import (
    BaseGoogleWalletObject,
    ButtonJWT,
    Comms,
)
from django.utils.html import format_html


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

    @classmethod
    def get_global_settings(cls, **kwargs):
        return OrderedDict(
            [
                (
                    "wallet_google_issuer_id",
                    forms.CharField(
                        label=_("Google Wallet Issuer/Merchant ID"),
                        help_text=_(
                            # TODO: update text
                            "After getting accepted by Google into the Google Pay API for Passes program, "
                            "your Issuer ID can be found in the Merchant center at "
                            "https://wallet.google.com/merchant/walletobjects/"
                        ),
                        required=False,
                    ),
                ),
                (
                    "wallet_google_credentials",
                    forms.FileField(
                        label=_("Google Wallet Service Account Credentials"),
                        help_text=_(
                            "Please paste the contents of the JSON credentials file "
                            "of the service account you tied to your Google Pay API "
                            "for Passes Issuer ID"
                        ),
                        required=False,
                        # TODO: add validator
                        # validators=[validate_json_credentials]
                    ),
                ),
                (
                    "wallet_google_instance_uuid",
                    forms.CharField(
                        label=_("Google Wallet Pass Instance UUID"),
                        help_text=_(
                            "Instance-specific part to be added to the wallet ids"
                        ),
                        required=False,
                    ),
                ),
            ]
        )

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

    def _get_jwt(self, ticket_objects):
        generated_jwt = self.comms.sign_jwt(
            ButtonJWT(
                origins=[settings.SITE_URL],
                issuer=self.comms.client_email,
                payload={"eventTicketObjects": ticket_objects},
                precreated=False,
            ).serialize()
        )

        # "The safe length of an encoded JWT is 1800 characters." https://developers.google.com/wallet/tickets/events/web
        if len(generated_jwt) > 1800:
            for to in dedup(ticket_objects):
                self.put_item_cached(to)
            generated_jwt = self.comms.sign_jwt(
                ButtonJWT(
                    origins=[settings.SITE_URL],
                    issuer=self.comms.client_email,
                    payload={"eventTicketObjects": ticket_objects},
                    precreated=True,
                ).serialize()
            )

        return f"https://pay.google.com/gp/v/save/{generated_jwt}"

    def generate(self, position, layout: PassStyle | None = None):
        # TODO?: early-exit caching (if object for position exists and layout is None)
        if not layout:
            layout = self.get_layout(position).pass_layout
        class_object, ticket_object = layout.generate(position)
        self.put_item_cached(class_object)

        return self._get_jwt([ticket_object])

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

        return self._get_jwt(ticket_objects)
