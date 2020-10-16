import base64
import struct

from cryptography.hazmat.backends.openssl.backend import Backend
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization.base import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key,
    load_pem_public_key,
)
from django.conf import settings
from django.dispatch import receiver
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Item, ItemVariation, SubEvent
from pretix.base.secretgenerators import pretix_sig1_pb2
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
                        current_secret: str = None, force_invalidate=False) -> str:
        """
        Generate a new secret for a ticket with product ``item``, variation ``variation``, subevent ``subevent``,
        and the current secret ``current_secret`` (if any).

        The result must be a string that should only contain the characters ``A-Za-z0-9+/=``.

        The algorithm is expected to conform to the following rules:

        If ``force_invalidate`` is set to ``True``, the method MUST return a different secret than ``current_secret``,
        such that ``current_secret`` can get revoked.

        If ``force_invalidate`` is set to ``False`` and ``item``, ``variation`` and ``subevent`` have the same value
        as when ``current_secret`` was generated, then this method MUST return ``current_secret`` unchanged.

        If ``force_invalidate`` is set to ``False`` and ``item``, ``variation`` and ``subevent`` have a different value
        as when ``current_secret`` was generated, then this method MAY OR MAY NOT return ``current_secret`` unchanged,
        depending on the semantics of the method.
        """
        raise NotImplementedError()


class RandomTicketSecretGenerator(BaseTicketSecretGenerator):
    verbose_name = _('Random (default, works with all pretix apps)')
    identifier = 'random'
    use_revocation_list = False

    def generate_secret(self, item: Item, variation: ItemVariation = None, subevent: SubEvent = None,
                        current_secret: str = None, force_invalidate=False):
        if current_secret and not force_invalidate:
            return current_secret
        return get_random_string(
            length=settings.ENTROPY['ticket_secret'],
            # Exclude o,0,1,i,l to avoid confusion with bad fonts/printers
            allowed_chars='abcdefghjkmnpqrstuvwxyz23456789'
        )


class Sig1TicketSecretGenerator(BaseTicketSecretGenerator):
    """
    Secret generator for signed QR codes.

    QR-code format:

    - 1 Byte with the version of the scheme, currently 0x01
    - 2 Bytes length of the payload (big-endian) => n
    - 2 Bytes length of the signature (big-endian) => m
    - n Bytes payload (with protobuf encoding)
    - m Bytes ECDSA signature of Sign(payload)

    The resulting string is REVERSED, to avoid all secrets of same length beginning with the same 10
    characters, which would make it impossible to search for secrets manually.
    """
    verbose_name = _('pretix signature scheme 1 (for very large events, does not work with pretixSCAN on iOS and '
                     'changes semantics of offline scanning – please refer to documentation or support for details)')
    identifier = 'pretix_sig1'
    use_revocation_list = True

    def _generate_keys(self):
        privkey = Ed25519PrivateKey.generate()
        pubkey = privkey.public_key()
        self.event.settings.ticket_secrets_pretix_sig1_privkey = base64.b64encode(privkey.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )).decode()
        self.event.settings.ticket_secrets_pretix_sig1_pubkey = base64.b64encode(pubkey.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )).decode()

    def _sign_payload(self, payload):
        if not self.event.settings.ticket_secrets_pretix_sig1_privkey:
            self._generate_keys()
        privkey = load_pem_private_key(
            base64.b64decode(self.event.settings.ticket_secrets_pretix_sig1_privkey), None, Backend()
        )
        signature = privkey.sign(payload)
        return (
            bytes([0x01])
            + struct.pack(">H", len(payload))
            + struct.pack(">H", len(signature))
            + payload
            + signature
        )

    def _parse(self, secret):
        try:
            rawbytes = base64.b64decode(secret[::-1])
            if rawbytes[0] != 1:
                raise ValueError('Invalid version')

            payload_len = struct.unpack(">H", rawbytes[1:3])[0]
            sig_len = struct.unpack(">H", rawbytes[3:5])[0]
            payload = rawbytes[5:5 + payload_len]
            signature = rawbytes[5 + payload_len:5 + payload_len + sig_len]
            pubkey = load_pem_public_key(
                base64.b64decode(self.event.settings.ticket_secrets_pretix_sig1_privkey), Backend()
            )
            pubkey.verify(signature, payload)
            t = pretix_sig1_pb2.Ticket()
            t.ParseFromString(payload)
            return t
        except ValueError:
            return None

    def generate_secret(self, item: Item, variation: ItemVariation = None, subevent: SubEvent = None,
                        current_secret: str = None, force_invalidate=False):
        if current_secret and not force_invalidate:
            ticket = self._parse(current_secret)
            if ticket:
                unchanged = (
                    ticket.item == item.pk and
                    ticket.variation == (variation.pk if variation else 0) and
                    ticket.subevent == (subevent.pk if subevent else 0)
                )
                if unchanged:
                    return current_secret

        t = pretix_sig1_pb2.Ticket()
        t.seed = get_random_string(9)
        t.item = item.pk
        t.variation = variation.pk if variation else 0
        t.subevent = subevent.pk if subevent else 0
        payload = t.SerializeToString()
        result = base64.b64encode(self._sign_payload(payload)).decode()[::-1]
        return result


@receiver(register_ticket_secret_generators, dispatch_uid="ticket_generator_default")
def recv_classic(sender, **kwargs):
    return [RandomTicketSecretGenerator, Sig1TicketSecretGenerator]


def assign_ticket_secret(event, position, force_invalidate=False, save=True):
    gen = event.ticket_secret_generator
    secret = gen.generate_secret(
        item=position.item,
        variation=position.variation,
        subevent=position.subevent,
        current_secret=position.secret,
        force_invalidate=force_invalidate
    )
    if position.secret and position.secret != secret and gen.use_revocation_list:
        position.revoked_secrets.create(event=event, secret=position.secret)
    position.secret = secret
    if save:
        position.save()
