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
import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Organizer
from pretix.base.secrets import (
    RandomTicketSecretGenerator, Sig1TicketSecretGenerator,
)

schemes = (
    (RandomTicketSecretGenerator, False),
    (Sig1TicketSecretGenerator, True),
)


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
    with scope(organizer=o):
        yield event


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_force_invalidate(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = g.generate_secret(item, None, None, current_secret=None, force_invalidate=False)
    assert first
    second = g.generate_secret(item, None, None, current_secret=first, force_invalidate=True)
    assert first != second


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_keep_same(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = g.generate_secret(item, None, None, current_secret=None, force_invalidate=False)
    assert first
    second = g.generate_secret(item, None, None, current_secret=first, force_invalidate=False)
    assert first == second


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_change_if_required(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    item2 = event.items.create(name="Bar", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = g.generate_secret(item, None, None, current_secret=None, force_invalidate=False)
    assert first
    second = g.generate_secret(item2, None, None, current_secret=first, force_invalidate=False)
    if input_dependent:
        assert first != second
    else:
        assert first == second


@pytest.mark.django_db
@pytest.mark.parametrize("scheme", schemes)
def test_change_if_invalid(event, scheme):
    item = event.items.create(name="Foo", default_price=0)
    generator, input_dependent = scheme
    g = generator(event)

    first = "blafasel"
    second = g.generate_secret(item, None, None, current_secret=first, force_invalidate=False)
    if input_dependent:
        assert first != second
