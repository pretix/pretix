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
from django.utils.crypto import get_random_string


def add_cart_session(client, event, data):
    new_id = get_random_string(length=32)
    session = client.session
    session['current_cart_event_{}'.format(event.pk)] = new_id
    if 'carts' not in session:
        session['carts'] = {}
    session['carts'][new_id] = data
    session.save()
    return new_id


def get_cart_session_key(client, event):
    cart_id = client.session.get('current_cart_event_{}'.format(event.pk))
    if cart_id:
        return cart_id
    else:
        return add_cart_session(client, event, {})
