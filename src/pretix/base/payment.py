from decimal import Decimal

from pretix.base.settings import SettingsSandbox


class BasePaymentProvider:
    """
    This is the base class for all payment providers.
    """

    def __init__(self, event):
        self.event = event
        self.settings = SettingsSandbox('payment', self.identifier, event)

    def __str__(self):
        return self.identifier

    @property
    def is_enabled(self):
        """
        Returns, whether or whether not this payment provider is enabled.
        By default, this is determined by the value of a setting.
        """
        return self.settings.get('_enabled', as_type=bool)

    def calculate_fee(self, price):
        """
        Calculate the fee for this payment provider which will be added to
        the final price if the price before fees (but after taxes) is 'price'.
        """
        fee_abs = self.settings.get('_fee_abs', as_type=Decimal, default=0)
        fee_percent = self.settings.get('_fee_percent', as_type=Decimal, default=0)
        return price * fee_percent / 100 + fee_abs

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this payment provider
        """
        raise NotImplementedError

    @property
    def identifier(self) -> str:
        """
        A unique identifier for this payment provider
        """
        raise NotImplementedError()

    @property
    def settings_form_fields(self) -> dict:
        """
        A dictionary. The keys should be (unprefixed) EventSetting keys,
        the values should be corresponding django form fields
        """
        raise NotImplementedError()
