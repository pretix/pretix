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

import ipaddress

_cgnat_net = ipaddress.ip_network('100.64.0.0/10')


def should_block_access(sa):
    ip_addr = ipaddress.ip_address(sa[0])
    check_ip4 = ip_addr.ipv4_mapped if getattr(ip_addr, "ipv4_mapped", None) else ip_addr
    if ip_addr.is_multicast:
        return True, f"Request to multicast address {sa[0]} blocked"
    if ip_addr.is_loopback or ip_addr.is_link_local:
        return True, f"Request to local address {sa[0]} blocked"
    if ip_addr.is_private:
        return True, f"Request to private address {sa[0]} blocked"
    if check_ip4 in _cgnat_net:
        return True, f"Request to RFC 6598 address {sa[0]} blocked"

    return False, None
