from django.conf import settings
from django.dispatch import receiver
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Item, ItemVariation, Seat, SubEvent
from pretix.base.signals import register_ticket_secret_generators


class BaseTicketSecretGenerator:
    """
    This is the base class to be used for all ticket secret generators.
    """

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this generator. This should be short but self-explanatory.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this renderer. This should only contain lowercase letters
        and in most cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    def __init__(self, event):
        self.event = event

    @property
    def use_revocation_list(self):
        """
        If this attribute is set to ``True``, the system will set all no-longer-used secrets on a revocation list.
        This is not required for pretix' default method of just using random identifiers as ticket secrets
        since all ticket scans will be compared to the database. However, if your secret generation method
        is designed to allow offline verification without a ticket database, all invalidated/replaced
        secrets as well as all secrets of canceled tickets will need to go to a revocation list.
        """
        return False

    def generate_secret(self, item: Item, variation: ItemVariation = None, subevent: SubEvent = None,
                        attendee_name: str = None, seat: Seat = None, current_secret: str = None,
                        force_invalidate=False) -> str:
        """
        Generate a new secret for a ticket with product ``item``, variation ``variation``, subevent ``subevent``,
        attendee name ``attendee_name``, seat `´seat`` and the current secret ``current_secret`` (if any).

        The result must be a string that should only contain the characters ``A-Za-z0-9+/=``.

        The algorithm is expected to conform to the following rules:

        If ``force_invalidate`` is set to ``True``, the method MUST return a different secret than ``current_secret``,
        such that ``current_secret`` can get revoked.

        If ``force_invalidate`` is set to ``False`` and ``item``, ``variation``, ``subevent``, ``attendee_name``,
        and ``seat`` have the same value as when ``current_secret`` was generated, then this method MUST return
        ``current_secret`` unchanged.
        """
        raise NotImplementedError()


class RandomTicketSecretGenerator(BaseTicketSecretGenerator):
    verbose_name = _('Random (default)')
    identifier = 'random'

    def generate_secret(self, item: Item, variation: ItemVariation = None, subevent: SubEvent = None,
                        attendee_name: str = None, seat: Seat = None, current_secret: str = None,
                        force_invalidate=False):
        if current_secret and not force_invalidate:
            return current_secret
        return get_random_string(
            length=settings.ENTROPY['ticket_secret'],
            # Exclude o,0,1,i,l to avoid confusion with bad fonts/printers
            allowed_chars='abcdefghjkmnpqrstuvwxyz23456789'
        )


@receiver(register_ticket_secret_generators, dispatch_uid="ticket_generator_default")
def recv_classic(sender, **kwargs):
    return [RandomTicketSecretGenerator]


def assign_ticket_secret(event, position, force_invalidate=False, save=True):
    gen = event.ticket_secret_generator
    secret = gen.generate_secret(
        item=position.item,
        variation=position.variation,
        subevent=position.subevent,
        attendee_name=position.attendee_name,
        seat=position.seat,
        current_secret=position.current_secret,
        force_invalidate=force_invalidate
    )
    if position.secrete and position.secret != secret and gen.use_revocation_list:
        position.revoked_secrets.create(event=event, secret=position.secret)

    if save:
        position.save()
