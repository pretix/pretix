import logging
from collections import OrderedDict

from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import register_sales_channels

logger = logging.getLogger(__name__)
_ALL_CHANNELS = None


class SalesChannel:
    def __repr__(self):
        return '<SalesChannel: {}>'.format(self.identifier)

    @property
    def identifier(self) -> str:
        """
        The internal identifier of this sales channel.
        """
        raise NotImplementedError()  # NOQA

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name of this sales channel.
        """
        raise NotImplementedError()  # NOQA

    @property
    def icon(self) -> str:
        """
        The name of a Font Awesome icon to represent this channel
        """
        return "circle"

    @property
    def testmode_supported(self) -> bool:
        """
        Indication, if a saleschannels supports test mode orders
        """
        return True

    @property
    def payment_restrictions_supported(self) -> bool:
        """
        If this property is ``True``, organizers can restrict the usage of payment providers to this sales channel.

        Example: pretixPOS provides its own sales channel, ignores the configured payment providers completely and
        handles payments locally. Therefor, this property should be set to ``False`` for the pretixPOS sales channel as
        the event organizer cannot restrict the usage of any payment provider through the backend.
        """
        return True


def get_all_sales_channels():
    global _ALL_CHANNELS

    if _ALL_CHANNELS:
        return _ALL_CHANNELS

    types = OrderedDict()
    for recv, ret in register_sales_channels.send(None):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.identifier] = r
        else:
            types[ret.identifier] = ret
    _ALL_CHANNELS = types
    return types


class WebshopSalesChannel(SalesChannel):
    identifier = "web"
    verbose_name = _('Online shop')
    icon = "globe"


@receiver(register_sales_channels, dispatch_uid="base_register_default_sales_channels")
def base_sales_channels(sender, **kwargs):
    return (
        WebshopSalesChannel(),
    )
