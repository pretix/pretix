from datetime import timedelta
from typing import List, Tuple

from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event
from pretix.base.signals import register_data_shredders


def shred_constraints(event: Event):
    if (event.date_to or event.date_from) > now() - timedelta(days=60):
        return _('Your event needs to be over for at least 60 days to use this feature.')
    if event.live:
        return _('Your ticket shop needs to be offline to use this feature.')
    return None


class BaseDataShredder:
    """
    This is the base class for all data shredders.
    """

    def __init__(self, event: Event):
        self.event = event

    def __str__(self):
        return self.identifier

    def generate_files(self) -> List[Tuple[str, str, str]]:
        """
        Export the data that is about to be shred and return a list of tuples consisting of a filename,
        a file type and file content.
        """
        raise NotImplementedError()  # NOQA

    def shred_data(self):
        """
        Actually remove the data.
        """
        raise NotImplementedError()  # NOQA

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this renderer. This should be short but
        self-explanatory. Good examples include 'German DIN 5008' or 'Italian invoice'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this shredder.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def description(self) -> str:
        """
        A description of what this shredder does. Can contain HTML.
        """
        raise NotImplementedError()  # NOQA


class EmailAddressShredder(BaseDataShredder):
    verbose_name = _('E-mail addresses')
    identifier = 'order_emails'
    description = _('This will remove all e-mail addresses from orders and attendees')

    def generate_files(self) -> List[Tuple[str, str, str]]:
        # TODO: Implement
        pass

    def shred_data(self):
        # TODO: Implement
        pass


@receiver(register_data_shredders, dispatch_uid="shredders_builtin")
def register_payment_provider(sender, **kwargs):
    return [EmailAddressShredder]
