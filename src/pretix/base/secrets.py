#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import base64
import inspect
import struct
from collections import namedtuple
from datetime import datetime
from typing import Optional

from cryptography.hazmat.backends.openssl.backend import Backend
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key,
    load_pem_public_key,
)
from django.dispatch import receiver
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from pretix.base.models import Item, ItemVariation, SubEvent
from pretix.base.secretgenerators import pretix_sig1_pb2
from pretix.base.signals import register_ticket_secret_generators

ParsedSecret = namedtuple('AnalyzedSecret', 'item variation subevent attendee_name opaque_id')


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

    def parse_secret(self, secret: str) -> Optional[ParsedSecret]:
        """
        Given a ``secret``, return an ``ParsedSecret`` with the information decoded from the secret, if possible.
        Any value of ``ParsedSecret`` may be ``None``, and if parsing is not possible at all, you can ``None`` (as
        the default implementation does).
        """
        return None

    def generate_secret(self, item: Item, variation: ItemVariation = None, subevent: SubEvent = None,
                        attendee_name: str = None, valid_from: datetime = None, valid_until: datetime = None,
                        current_secret: str = None, force_invalidate=False) -> str:
        """
        Generate a new secret for a ticket with product ``item``, variation ``variation``, subevent ``subevent``,
        attendee name ``attendee_name`` (can be ``None``), earliest validity ``valid_from``, lastest validity
         ``valid_until``, and the current secret ``current_secret`` (if any).

        The result must be a string that should only contain the characters ``A-Za-z0-9+/=``.

        The algorithm is expected to conform to the following rules:

        If ``force_invalidate`` is set to ``True``, the method MUST return a different secret than ``current_secret``,
        such that ``current_secret`` can get revoked.

        If ``force_invalidate`` is set to ``False`` and ``item``, ``variation`` and ``subevent`` have the same value
        as when ``current_secret`` was generated, then this method MUST return ``current_secret`` unchanged.

        If ``force_invalidate`` is set to ``False`` and ``item``, ``variation`` and ``subevent`` have a different value
        as when ``current_secret`` was generated, then this method MAY OR MAY NOT return ``current_secret`` unchanged,
        depending on the semantics of the method.

        .. note:: While it is guaranteed that ``generate_secret`` and the revocation list process are called every
                  time the ``item``, ``variation``, or ``subevent`` parameters change, it is currently **NOT**
                  guaranteed that this process is triggered if the ``attendee_name`` parameter changes. You should
                  therefore not rely on this value for more than informational or debugging purposes.
        """
        raise NotImplementedError()


class RandomTicketSecretGenerator(BaseTicketSecretGenerator):
    verbose_name = _('Random (default, works with all pretix apps)')
    identifier = 'random'
    use_revocation_list = False

    def generate_secret(self, item: Item, variation: ItemVariation = None, subevent: SubEvent = None,
                        attendee_name: str = None, valid_from: datetime = None, valid_until: datetime = None,
                        current_secret: str = None, force_invalidate=False) -> str:
        if current_secret and not force_invalidate:
            return current_secret
        return get_random_string(
            length=self.event.settings.ticket_secret_length,
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
    verbose_name = _('pretix signature scheme 1 (for very large events, changes semantics of offline scanning – '
                     'please refer to documentation or support for details)')
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
                base64.b64decode(self.event.settings.ticket_secrets_pretix_sig1_pubkey), Backend()
            )
            pubkey.verify(signature, payload)
            t = pretix_sig1_pb2.Ticket()
            t.ParseFromString(payload)
            return t
        except:
            return None

    def parse_secret(self, secret: str) -> Optional[ParsedSecret]:
        ticket = self._parse(secret)
        if ticket:
            item = self.event.items.filter(pk=ticket.item).first() if ticket.item else None
            subevent = self.event.subevents.filter(pk=ticket.subevent).first() if ticket.subevent else None
            variation = item.variations.filter(pk=ticket.variation).first() if item and ticket.subevent else None
            opaque_id = ticket.seed
            return self.ParsedSecret(item=item, subevent=subevent, variation=variation, opaque_id=opaque_id, attendee_name=None)

    def _encode_time(self, t):
        if t is None:
            return 0
        return int(t.timestamp())

    def generate_secret(self, item: Item, variation: ItemVariation = None, subevent: SubEvent = None,
                        attendee_name: str = None, valid_from: datetime = None, valid_until: datetime = None,
                        current_secret: str = None, force_invalidate=False) -> str:
        if current_secret and not force_invalidate:
            ticket = self._parse(current_secret)
            if ticket:
                unchanged = (
                    ticket.item == item.pk and
                    ticket.variation == (variation.pk if variation else 0) and
                    ticket.subevent == (subevent.pk if subevent else 0) and
                    ticket.validFromUnixTime == self._encode_time(valid_from) and
                    ticket.validUntilUnixTime == self._encode_time(valid_until)
                )
                if unchanged:
                    return current_secret

        t = pretix_sig1_pb2.Ticket()
        t.seed = get_random_string(9)
        t.item = item.pk
        t.variation = variation.pk if variation else 0
        t.subevent = subevent.pk if subevent else 0
        t.validFromUnixTime = self._encode_time(valid_from)
        t.validUntilUnixTime = self._encode_time(valid_until)
        payload = t.SerializeToString()
        result = base64.b64encode(self._sign_payload(payload)).decode()[::-1]
        return result


@receiver(register_ticket_secret_generators, dispatch_uid="ticket_generator_default")
def recv_classic(sender, **kwargs):
    return [RandomTicketSecretGenerator, Sig1TicketSecretGenerator]


def assign_ticket_secret(event, position, force_invalidate_if_revokation_list_used=False, force_invalidate=False, save=True):
    gen = event.ticket_secret_generator
    if gen.use_revocation_list and force_invalidate_if_revokation_list_used:
        force_invalidate = True

    kwargs = {}
    params = inspect.signature(gen.generate_secret).parameters
    if 'attendee_name' in params:
        kwargs['attendee_name'] = position.attendee_name
    if 'valid_from' in params:
        kwargs['valid_from'] = position.valid_from
    if 'valid_until' in params:
        kwargs['valid_until'] = position.valid_until
    secret = gen.generate_secret(
        item=position.item,
        variation=position.variation,
        subevent=position.subevent,
        current_secret=position.secret,
        force_invalidate=force_invalidate,
        **kwargs
    )
    changed = position.secret != secret
    if position.secret and changed and gen.use_revocation_list and position.pk:
        position.revoked_secrets.create(event=event, secret=position.secret)
    position.secret = secret
    if save and changed:
        position.save()
