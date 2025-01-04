from decimal import Decimal

from pretix.base.storelogic import IncompleteError
from pretix.base.storelogic.addons import (
    addons_is_applicable, addons_is_completed,
)
from pretix.base.storelogic.fields import ensure_fields_are_completed


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


def get_steps(event, cart_positions, invoice_address, cart_session, total):
    return [
        AddonStep(event, cart_positions, invoice_address, cart_session, total),
        FieldsStep(event, cart_positions, invoice_address, cart_session, total),
        # todo: cross-selling
        # todo: customers
        # todo: memberships
        # todo: plugin signals
        # todo: payment
        # todo: confirmations
    ]
