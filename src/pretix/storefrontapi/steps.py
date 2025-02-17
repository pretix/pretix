from collections import UserDict
from decimal import Decimal

from django.test import RequestFactory

from pretix.base.storelogic import IncompleteError
from pretix.base.storelogic.addons import (
    addons_is_applicable, addons_is_completed,
)
from pretix.base.storelogic.fields import ensure_fields_are_completed
from pretix.base.storelogic.payment import (
    ensure_payment_is_completed, payment_is_applicable,
)


class CheckoutStep:
    def __init__(self, event, cart_positions, invoice_address, cart_session, total):
        self.event = event
        self.cart_positions = cart_positions
        self.cart_session = cart_session
        self.invoice_address = invoice_address
        self.total = total

    @property
    def identifier(self):
        raise NotImplementedError()

    def is_applicable(self):
        raise NotImplementedError()

    def is_valid(self):
        raise NotImplementedError()


class AddonStep(CheckoutStep):
    identifier = "addons"

    def is_applicable(self):
        return addons_is_applicable(self.cart_positions)

    def is_valid(self):
        return addons_is_completed(self.cart_positions)


class FieldsStep(CheckoutStep):
    identifier = "fields"

    def is_applicable(self):
        return True

    def is_valid(self):
        try:
            ensure_fields_are_completed(
                self.event,
                self.cart_positions,
                self.cart_session,
                self.invoice_address,
                False,
                cart_is_free=self.total == Decimal("0.00"),
            )
        except IncompleteError:
            return False
        else:
            return True


class PaymentStep(CheckoutStep):
    identifier = "payment"

    @property
    def request(self):
        # TODO: find a better way to avoid this
        rf = RequestFactory()
        r = rf.get("/")
        r.event = self.event
        r.organizer = self.event.organizer
        self.cart_session.setdefault("fake_request", {})
        cart_id = self.cart_positions[0].cart_id if self.cart_positions else None
        r.session = UserDict(
            {
                f"current_cart_event_{self.event.pk}": cart_id,
                "carts": {cart_id: self.cart_session},
            } if cart_id else {}
        )
        r.session.session_key = cart_id
        return r

    def is_applicable(self):
        return payment_is_applicable(
            self.event,
            self.total,
            self.cart_positions,
            self.invoice_address,
            self.cart_session,
            self.request,
        )

    def is_valid(self):
        try:
            ensure_payment_is_completed(
                self.event,
                self.total,
                self.cart_session,
                self.request,
            )
        except IncompleteError:
            return False
        else:
            return True


def get_steps(event, cart_positions, invoice_address, cart_session, total):
    return [
        AddonStep(event, cart_positions, invoice_address, cart_session, total),
        FieldsStep(event, cart_positions, invoice_address, cart_session, total),
        PaymentStep(event, cart_positions, invoice_address, cart_session, total),
        # todo: cross-selling
        # todo: customers
        # todo: memberships
        # todo: plugin signals
        # todo: confirmations
    ]
