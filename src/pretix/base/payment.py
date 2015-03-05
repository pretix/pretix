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
