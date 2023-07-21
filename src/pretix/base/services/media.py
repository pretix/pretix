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
import secrets

from django.db import IntegrityError
from django.db.models import Q
from django_scopes import scopes_disabled

from pretix.base.models import GiftCardAcceptance
from pretix.base.models.media import MediumKeySet


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
