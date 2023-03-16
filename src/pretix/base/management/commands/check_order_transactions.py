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
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import models
from django.db.models import (
    Case, Count, F, OuterRef, Q, Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce
from django_scopes import scopes_disabled

from pretix.base.models import Order, OrderFee, OrderPosition
from pretix.base.models.orders import Transaction


class Command(BaseCommand):
    help = "Check order for consistency with their transactions"

    @scopes_disabled()
    def handle(self, *args, **options):
        qs = Order.objects.annotate(
            position_total=Coalesce(
                Subquery(
                    OrderPosition.objects.filter(
                        order=OuterRef('pk')
                    ).order_by().values('order').annotate(p=Sum('price')).values('p'),
                    output_field=models.DecimalField(decimal_places=2, max_digits=13)
                ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=13)
            ),
            position_cnt=Case(
                When(Q(status__in=('e', 'c')) | Q(require_approval=True), then=Value(0)),
                default=Coalesce(
                    Subquery(
                        OrderPosition.objects.filter(
                            order=OuterRef('pk')
                        ).order_by().values('order').annotate(p=Count('*')).values('p'),
                        output_field=models.IntegerField()
                    ), Value(0), output_field=models.IntegerField()
                ),
                output_field=models.IntegerField()
            ),
            fee_total=Coalesce(
                Subquery(
                    OrderFee.objects.filter(
                        order=OuterRef('pk')
                    ).order_by().values('order').annotate(p=Sum('value')).values('p'),
                    output_field=models.DecimalField(decimal_places=2, max_digits=13)
                ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=13)
            ),
            tx_total=Coalesce(
                Subquery(
                    Transaction.objects.filter(
                        order=OuterRef('pk')
                    ).order_by().values('order').annotate(p=Sum(F('price') * F('count'))).values('p'),
                    output_field=models.DecimalField(decimal_places=2, max_digits=13)
                ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=13)
            ),
            tx_cnt=Coalesce(
                Subquery(
                    Transaction.objects.filter(
                        order=OuterRef('pk'),
                        item__isnull=False,
                    ).order_by().values('order').annotate(p=Sum(F('count'))).values('p'),
                    output_field=models.DecimalField(decimal_places=2, max_digits=13)
                ), Value(0), output_field=models.DecimalField(decimal_places=2, max_digits=13)
            ),
        ).annotate(
            correct_total=Case(
                When(Q(status=Order.STATUS_CANCELED) | Q(status=Order.STATUS_EXPIRED) | Q(require_approval=True),
                     then=Value(0)),
                default=F('position_total') + F('fee_total'),
                output_field=models.DecimalField(decimal_places=2, max_digits=13)
            ),
        ).exclude(
            total=F('position_total') + F('fee_total'),
            tx_total=F('correct_total'),
            tx_cnt=F('position_cnt')
        ).select_related('event')
        for o in qs:
            if abs(o.tx_total - o.correct_total) < Decimal('0.00001') and abs(o.position_total + o.fee_total - o.total) < Decimal('0.00001') \
                    and o.tx_cnt == o.position_cnt:
                # Ignore SQLite which treats Decimals like floats…
                continue
            print(f"Error in order {o.full_code}: status={o.status}, sum(positions)+sum(fees)={o.position_total + o.fee_total}, "
                  f"order.total={o.total}, sum(transactions)={o.tx_total}, expected={o.correct_total}, pos_cnt={o.position_cnt}, tx_pos_cnt={o.tx_cnt}")

        self.stderr.write(self.style.SUCCESS('Check completed.'))
