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
from typing import List, Union

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import (
    SearchQuery, SearchVector, SearchVectorField,
)
from django.db import models
from django.db.models import Value
from django_scopes.manager import ScopedManager

from pretix.base.models import (
    Event, Invoice, InvoiceAddress, Order, OrderPayment, OrderPosition,
    OrderRefund, Organizer,
)


class SearchIndexQuerySet(models.QuerySet):
    def search_for(self, query: str):
        sq = SearchQuery(query, config="pretix_search", search_type="raw")  # todo: probably use plain
        if query.count(" ") < 1 and "@" not in query:
            # Order code normalization, only apply for one-word search that is not an email address
            sq |= SearchQuery(Order.normalize_code(query.rsplit("-", 1)[-1]), config="pretix_search", search_type="plain")

            if query.isdigit():
                for i in range(2, 12):
                    sq |= SearchQuery(query.zfill(i), config="pretix_search", search_type="plain")

        return self.filter(search_vector=sq)


class OrderSearchIndex(models.Model):
    organizer = models.ForeignKey(Organizer, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    orderposition = models.OneToOneField(
        OrderPosition,
        on_delete=models.CASCADE,
        related_name="search_index",
        null=True,
        blank=True,
    )
    orderpayment = models.OneToOneField(
        OrderPayment,
        on_delete=models.CASCADE,
        related_name="search_index",
        null=True,
        blank=True,
    )
    orderrefund = models.OneToOneField(
        OrderRefund,
        on_delete=models.CASCADE,
        related_name="search_index",
        null=True,
        blank=True,
    )
    invoiceaddress = models.OneToOneField(
        InvoiceAddress,
        on_delete=models.CASCADE,
        related_name="search_index",
        null=True,
        blank=True,
    )
    invoice = models.OneToOneField(
        Invoice,
        on_delete=models.CASCADE,
        related_name="search_index",
        null=True,
        blank=True,
    )
    last_modified = models.DateTimeField(auto_now=True)
    search_vector = SearchVectorField()

    objects = ScopedManager(SearchIndexQuerySet.as_manager().__class__, organizer='organizer')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(
                    orderposition__isnull=True,
                    orderpayment__isnull=True,
                    orderrefund__isnull=True,
                    invoiceaddress__isnull=True,
                    invoice__isnull=True,
                ),
                fields=("order",),
                name="ordersearchindex_one_per_order",
            ),
        ]
        indexes = [
            GinIndex("search_vector", name="ordersearchindex_vector"),
        ]

    def save(self, *args, **kwargs):
        fields_filled = [
            bool(self.orderposition_id),
            bool(self.orderpayment_id),
            bool(self.orderrefund_id),
            bool(self.invoiceaddress_id),
            bool(self.invoice_id),
        ]
        if fields_filled.count(True) > 1:
            raise ValueError("A OrderSearchIndex may one relate to one other instance")
        super().save(*args, **kwargs)

    @classmethod
    def update_for(cls, obj: Union[Order, OrderPayment, OrderPosition, OrderRefund], inputs: List[str]):
        index_text = "\n".join([i for i in inputs if i])
        if isinstance(obj, Order):
            order = obj
        else:
            order = obj.order

        kwargs = dict(
            order=order,
            orderpayment=obj if isinstance(obj, OrderPayment) else None,
            orderrefund=obj if isinstance(obj, OrderRefund) else None,
            orderposition=obj if isinstance(obj, OrderPosition) else None,
            invoiceaddress=obj if isinstance(obj, InvoiceAddress) else None,
            invoice=obj if isinstance(obj, Invoice) else None,
        )

        if not index_text.strip():
            OrderSearchIndex.objects.filter(**kwargs).delete()
        else:
            OrderSearchIndex.objects.update_or_create(
                **kwargs,
                defaults=dict(
                    search_vector=SearchVector(
                        Value(index_text),
                        config="pretix_search"
                    ),
                ),
                create_defaults=dict(
                    event_id=order.event_id,
                    organizer_id=order.organizer_id,
                ),
            )
