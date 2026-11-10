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
from pretix.base.services.quotas import QuotaAvailability


def prepare_quotas_for_boxes(quotas):
    qa = QuotaAvailability(early_out=False)
    for q in quotas:
        qa.queue(q)
    qa.compute()

    for q in quotas:
        q.cached_avail = qa.results[q]
        q.cached_availability_paid_orders = qa.count_paid_orders.get(q, 0)
        q.used = (
            qa.count_paid_orders.get(q, 0) +
            qa.count_pending_orders.get(q, 0) +
            qa.count_exited_orders.get(q, 0) +
            qa.count_vouchers.get(q, 0) +
            qa.count_waitinglist.get(q, 0) +
            qa.count_cart.get(q, 0)
        )
        if q.size is not None:
            other_blocked = q.size - q.cached_availability_paid_orders - q.cached_avail[1]
            q.percent_paid = min(
                100,
                round(q.cached_availability_paid_orders / q.size * 100) if q.size > 0 else 100
            )
            q.percent_other = min(
                100,
                round(other_blocked / q.size * 100) if q.size > 0 else 100
            )
