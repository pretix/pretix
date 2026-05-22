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
import time

from django.core.management.base import BaseCommand
from django_scopes import scopes_disabled
from tqdm import tqdm

from pretix.base.models import (
    Invoice, InvoiceAddress, Order, OrderPayment, OrderPosition, OrderRefund,
)


class Command(BaseCommand):
    help = "Recreate order search index"

    def add_arguments(self, parser):
        parser.add_argument(
            "--slowdown",
            dest="interval",
            type=int,
            default=0,
            help="Interval for staggered execution. If set to a value different then zero, we will "
                 "wait this many milliseconds between every order we process.",
        )

    @scopes_disabled()
    def handle(self, *args, **options):
        querysets = [
            Order.objects.all(),
            OrderPosition.all.all(),
            OrderPayment.objects.all(),
            OrderRefund.objects.all(),
            InvoiceAddress.objects.filter(order__isnull=False),
            Invoice.objects.all(),
        ]

        for qs in querysets:
            last_pk = 0
            with tqdm(total=qs.count()) as pbar:
                while True:
                    batch = list(qs.filter(pk__gt=last_pk)[:5000])
                    if not batch:
                        break

                    for o in batch:
                        o._update_search_index()
                        time.sleep(0)
                        pbar.update(1)
                    last_pk = batch[-1].pk
