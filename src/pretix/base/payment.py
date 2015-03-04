class BasePaymentProvider:
    """
    This is the base class for all payment providers.
    """

    def get_identifier(self) -> str:
        """
        Return a unique identifier for this payment provider
        """
        raise NotImplementedError()
