from pretix.base.storelogic.addons import (
    addons_is_applicable, addons_is_completed,
)


class CheckoutStep:
    def __init__(self, event, cart_positions):
        self.event = event
        self.cart_positions = cart_positions

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


def get_steps(event, cart_positions):
    return [
        AddonStep(event, cart_positions),
        # todo: cross-selling
        # todo: customers
        # todo: memberships
        # todo: questions
        # todo: plugin signals
        # todo: payment
        # todo: confirmations
    ]
