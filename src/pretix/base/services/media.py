#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import secrets

from django.db import IntegrityError
from django.db.models import Q
from django.utils.translation import gettext as _
from django_scopes import scopes_disabled

from pretix.base.media import MEDIA_TYPES
from pretix.base.models import Checkin, GiftCardAcceptance, Item
from pretix.base.models.media import MediumKeySet, ReusableMedium
from pretix.base.services.checkin import CheckInError


def create_nfc_mf0aes_keyset(organizer):
    for i in range(20):
        public_id = secrets.randbelow(2 ** 32)
        uid_key = secrets.token_bytes(16)
        diversification_key = secrets.token_bytes(16)
        try:
            return MediumKeySet.objects.create(
                organizer=organizer,
                media_type="nfc_mf0aes",
                public_id=public_id,
                diversification_key=diversification_key,
                uid_key=uid_key,
                active=True,
            )
        except IntegrityError:  # either race condition with another thread or duplicate public ID
            try:
                return MediumKeySet.objects.get(
                    organizer=organizer,
                    media_type="nfc_mf0aes",
                    active=True,
                )
            except MediumKeySet.DoesNotExist:
                continue  # duplicate public ID, let's try again


@scopes_disabled()
def get_keysets_for_organizer(organizer):
    sets = list(MediumKeySet.objects.filter(
        Q(organizer=organizer) | Q(organizer__in=GiftCardAcceptance.objects.filter(
            acceptor=organizer,
            active=True,
            reusable_media=True,
        ).values_list("issuer_id", flat=True))
    ))
    if organizer.settings.reusable_media_type_nfc_mf0aes and not any(
        ks.organizer == organizer and ks.media_type == "nfc_mf0aes" for ks in sets
    ):
        new_set = create_nfc_mf0aes_keyset(organizer)
        if new_set:
            sets.append(new_set)
    return sets


def perform_media_exchange(organizer, media_type, identifier, link_orderposition, user, auth):
    """
    Create or retrieve a medium, then link the order position to it. Expected to be called in a transaction.

    :param organizer: Organizer to operate in
    :param media_type: Type of medium to operate with
    :param identifier: Identifier of the medium
    :param link_orderposition: Position to link to the medium
    :return: ReusableMedium
    """
    medium = None
    media_policy = link_orderposition.item.media_policy

    if media_type not in MEDIA_TYPES:  # should be caught by serializer already
        raise CheckInError(
            _('Invalid medium type.'),
            Checkin.REASON_ERROR,
            reason=_('Invalid medium type.'),
        )

    if not MEDIA_TYPES[media_type].is_active(organizer):
        raise CheckInError(
            _('Medium type is not enabled for organizer.'),
            Checkin.REASON_ERROR,
            reason=_('Medium type is not enabled for organizer.'),
        )

    if link_orderposition.item.media_type != media_type:
        raise CheckInError(
            _('Incorrect medium type for product.'),
            Checkin.REASON_PRODUCT,
            reason=_('Incorrect medium type for product.'),
        )

    if link_orderposition.linked_media.exists():
        raise CheckInError(
            _('Ticket is already exchanged for reusable medium.'),
            Checkin.REASON_ALREADY_EXCHANGED,
            reason=_('Ticket is already exchanged for reusable medium.'),
        )

    if media_policy in (Item.MEDIA_POLICY_APPEND, Item.MEDIA_POLICY_APPEND_OR_NEW, Item.MEDIA_POLICY_NEW):
        link_action = "append"
    else:
        link_action = "replace"

    if media_policy in (Item.MEDIA_POLICY_REUSE, Item.MEDIA_POLICY_APPEND):
        try:
            medium = ReusableMedium.objects.get(
                type=media_type,
                identifier=identifier,
                organizer=organizer,
            )
        except ReusableMedium.DoesNotExist:
            raise CheckInError(
                _('Reusable medium not found.'),
                Checkin.REASON_MEDIUM_INVALID,
                reason=_('Reusable medium not found.'),
            )
        else:
            if medium.is_expired or not medium.active:
                raise CheckInError(
                    _('Reusable medium is inactive or expired.'),
                    Checkin.REASON_MEDIUM_INVALID,
                    reason=_('Reusable medium is inactive or expired.'),
                )

    elif media_policy in (Item.MEDIA_POLICY_REUSE_OR_NEW, Item.MEDIA_POLICY_APPEND_OR_NEW):
        try:
            medium = ReusableMedium.objects.get(
                type=media_type,
                identifier=identifier,
                organizer=organizer,
            )
        except ReusableMedium.DoesNotExist:
            if not MEDIA_TYPES[media_type].medium_created_from_unknown_supported:
                raise CheckInError(
                    _('Reusable medium not found and could not be created.'),
                    Checkin.REASON_MEDIUM_INVALID,
                )

            medium = MEDIA_TYPES[media_type].handle_unknown(organizer, identifier, user, auth, force_create=True)
            if not medium:
                raise CheckInError(
                    _('Reusable medium not found and could not be created.'),
                    Checkin.REASON_MEDIUM_INVALID,
                )

        if medium.is_expired or not medium.active:
            raise CheckInError(
                _('Reusable medium is inactive or expired.'),
                Checkin.REASON_MEDIUM_INVALID,
                reason=_('Reusable medium is inactive or expired.'),
            )

    elif media_policy == Item.MEDIA_POLICY_NEW:
        if not MEDIA_TYPES[media_type].medium_created_from_unknown_supported:
            raise CheckInError(
                _('Reusable medium not found and could not be created.'),
                Checkin.REASON_MEDIUM_INVALID,
            )
        try:
            medium = MEDIA_TYPES[media_type].handle_unknown(organizer, identifier, user, auth, force_create=True)
        except IntegrityError:
            raise CheckInError(
                _('Reusable medium already exists.'),
                Checkin.REASON_MEDIUM_EXISTS,
            )
        else:
            if not medium:
                raise CheckInError(
                    _('Reusable medium could not be created.'),
                    Checkin.REASON_MEDIUM_INVALID,
                )

    else:
        raise CheckInError(
            _('Product does not support medium exchange.'),
            Checkin.REASON_PRODUCT,
            reason=_('Product does not support medium exchange.'),
        )

    if link_action == 'append':
        medium.linked_orderpositions.add(link_orderposition)
        medium.log_action(
            'pretix.reusable_medium.linked_orderposition.added',
            user=user,
            auth=auth,
            data={
                'linked_orderposition': link_orderposition,
            }
        )
    elif link_action == 'replace':
        already_found = False
        for op_pk in medium.linked_orderpositions.values_list('pk', flat=True):
            if op_pk == link_orderposition.pk:
                already_found = True
                continue
            else:
                medium.log_action(
                    'pretix.reusable_medium.linked_orderposition.removed',
                    data={
                        'linked_orderposition': op_pk,
                    }
                )
        if not already_found:
            medium.linked_orderpositions.set([link_orderposition])
            medium.log_action(
                'pretix.reusable_medium.linked_orderposition.added',
                user=user,
                auth=auth,
                data={
                    'linked_orderposition': link_orderposition,
                }
            )

    link_orderposition.order.log_action(
        'pretix.reusable_medium.exchanged',
        data={
            'position': link_orderposition.pk,
            'positionid': link_orderposition.positionid,
            'medium': medium.pk,
            'medium_identifier': medium.identifier,
            'medium_type': medium.media_type.identifier,
        }
    )
    medium.touch()

    return medium
