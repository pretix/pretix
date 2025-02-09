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
import json
from collections import namedtuple

import jsonschema
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Exists, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Power
from django.utils.deconstruct import deconstructible
from django.utils.timezone import now
from django.utils.translation import gettext, gettext_lazy as _

from pretix.base.models import Event, Item, LoggedModel, Organizer, SubEvent


@deconstructible
class SeatingPlanLayoutValidator:
    def __call__(self, value):
        if not isinstance(value, dict):
            try:
                val = json.loads(value)
            except ValueError:
                raise ValidationError(_('Your layout file is not a valid JSON file.'))
        else:
            val = value
        with open(finders.find('seating/seating-plan.schema.json'), 'r') as f:
            schema = json.loads(f.read())
        try:
            jsonschema.validate(val, schema)
        except jsonschema.ValidationError as e:
            e = str(e).replace('%', '%%')
            raise ValidationError(_('Your layout file is not a valid seating plan. Error message: {}').format(e))

        try:
            seat_guids = set()
            for z in val["zones"]:
                for r in z["rows"]:
                    for s in r["seats"]:
                        if not s.get("seat_guid"):
                            raise ValidationError(
                                _("Seat with zone {zone}, row {row}, and number {number} has no seat ID.").format(
                                    zone=z["name"],
                                    row=r["row_number"],
                                    number=s["seat_number"],
                                )
                            )
                        elif s["seat_guid"] in seat_guids:
                            raise ValidationError(
                                _("Multiple seats have the same ID: {id}").format(
                                    id=s["seat_guid"],
                                )
                            )

                        seat_guids.add(s["seat_guid"])
        except ValidationError as e:
            raise ValidationError(_('Your layout file is not a valid seating plan. Error message: {}').format(", ".join(e.message for e in e.error_list)))


class SeatingPlan(LoggedModel):
    """
    Represents an abstract seating plan, without relation to any event.
    """
    name = models.CharField(max_length=190, verbose_name=_('Name'))
    organizer = models.ForeignKey(Organizer, related_name='seating_plans', on_delete=models.CASCADE)
    layout = models.TextField(validators=[SeatingPlanLayoutValidator()])

    Category = namedtuple('Categrory', 'name')
    RawSeat = namedtuple('Seat', 'guid number row category zone sorting_rank row_label seat_label x y')

    def __str__(self):
        return self.name

    @property
    def layout_data(self):
        return json.loads(self.layout)

    @layout_data.setter
    def layout_data(self, v):
        self.layout = json.dumps(v)

    def get_categories(self):
        return [
            self.Category(name=c['name'])
            for c in self.layout_data['categories']
        ]

    def iter_all_seats(self):
        # This returns all seats in a plan and assignes each of them a rank. The rank is used for sorting lists of
        # seats later. The rank does not say anything about the *quality* of a seat, and is only meant as a heuristic
        # to make it easier for humas to process lists of seats. The current algorithm assumes that there are less
        # than 10'000 zones, less than 10'000 rows in every zone and less than 10'000 seats in every row.
        # Respectively, no row/seat numbers may be numeric with a value of 10'000 or more. The resulting ranks
        # *will* have gaps. We chose this way over just sorting the seats and continuously enumerating them as an
        # optimization, because this way we do not need to update the rank of very seat if we change a plan a little.
        for zi, z in enumerate(self.layout_data['zones']):
            zpos = (z['position']['x'], z['position']['y'])
            for ri, r in enumerate(z['rows']):
                rpos = (zpos[0] + r['position']['x'], zpos[1] + r['position']['y'])
                row_label = None
                if r.get('row_label'):
                    row_label = r['row_label'].replace("%s", r.get('row_number', str(ri)))
                try:
                    row_rank = int(r['row_number'])
                except ValueError:
                    row_rank = ri
                for si, s in enumerate(r['seats']):
                    seat_label = None
                    if r.get('seat_label'):
                        seat_label = r['seat_label'].replace("%s", s.get('seat_number', str(si)))
                    try:
                        seat_rank = int(s['seat_number'])
                    except ValueError:
                        seat_rank = si
                    rank = (
                        10000 * 10000 * zi + 10000 * row_rank + seat_rank
                    )

                    yield self.RawSeat(
                        number=s['seat_number'],
                        guid=s['seat_guid'],
                        row=r['row_number'],
                        row_label=row_label,
                        seat_label=seat_label,
                        zone=z['name'],
                        category=s['category'],
                        sorting_rank=rank,
                        x=rpos[0] + s['position']['x'],
                        y=rpos[1] + s['position']['y'],
                    )


class SeatCategoryMapping(models.Model):
    """
    Input seating plans have abstract "categories", such as "Balcony seat", etc. This model maps them to actual
    pretix product on a per-(sub)event level.
    """
    event = models.ForeignKey(Event, related_name='seat_category_mappings', on_delete=models.CASCADE)
    subevent = models.ForeignKey(SubEvent, null=True, blank=True, related_name='seat_category_mappings', on_delete=models.CASCADE)
    layout_category = models.CharField(max_length=190)
    product = models.ForeignKey(Item, related_name='seat_category_mappings', on_delete=models.CASCADE)


class Seat(models.Model):
    """
    This model is used to represent every single specific seat within an (sub)event that can be selected. It's mainly
    used for internal bookkeeping and not to be modified by users directly.
    """
    event = models.ForeignKey(Event, related_name='seats', on_delete=models.CASCADE)
    subevent = models.ForeignKey(SubEvent, null=True, blank=True, related_name='seats', on_delete=models.CASCADE)
    zone_name = models.CharField(max_length=190, blank=True, default="")
    row_name = models.CharField(max_length=190, blank=True, default="")
    row_label = models.CharField(max_length=190, null=True)
    seat_number = models.CharField(max_length=190, blank=True, default="")
    seat_label = models.CharField(max_length=190, null=True)
    seat_guid = models.CharField(max_length=190, db_index=True)
    product = models.ForeignKey('Item', null=True, blank=True, related_name='seats', on_delete=models.SET_NULL)
    blocked = models.BooleanField(default=False)
    sorting_rank = models.BigIntegerField(default=0)
    x = models.FloatField(null=True)
    y = models.FloatField(null=True)

    class Meta:
        ordering = ['sorting_rank', 'seat_guid']

    @property
    def name(self):
        return str(self)

    def __str__(self):
        parts = []
        if self.zone_name:
            parts.append(self.zone_name)

        if self.row_label:
            parts.append(self.row_label)
        elif self.row_name:
            parts.append(gettext('Row {number}').format(number=self.row_name))

        if self.seat_label:
            parts.append(self.seat_label)
        elif self.seat_number:
            parts.append(gettext('Seat {number}').format(number=self.seat_number))

        if not parts:
            return self.seat_guid
        return ', '.join(parts)

    @classmethod
    def annotated(cls, qs, event_id, subevent, ignore_voucher_id=None, minimal_distance=0,
                  ignore_order_id=None, ignore_cart_id=None, distance_only_within_row=False, annotate_ids=False):
        from . import CartPosition, Order, OrderPosition, Voucher

        vqs = Voucher.objects.filter(
            event_id=event_id,
            subevent=subevent,
            seat_id=OuterRef('pk'),
            redeemed__lt=F('max_usages'),
        ).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=now())
        )
        if ignore_voucher_id:
            vqs = vqs.exclude(pk=ignore_voucher_id)
        opqs = OrderPosition.objects.filter(
            order__event_id=event_id,
            subevent=subevent,
            seat_id=OuterRef('pk'),
            order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID]
        )
        if ignore_order_id:
            opqs = opqs.exclude(order_id=ignore_order_id)
        cqs = CartPosition.objects.filter(
            event_id=event_id,
            subevent=subevent,
            seat_id=OuterRef('pk'),
            expires__gte=now()
        )
        if ignore_cart_id:
            cqs = cqs.exclude(cart_id=ignore_cart_id)
        if annotate_ids:
            qs_annotated = qs.annotate(
                orderposition_id=Subquery(opqs.values('id')),
                cartposition_id=Subquery(cqs.values('id')),
                voucher_id=Subquery(vqs.values('id')),
            )
        else:
            qs_annotated = qs.annotate(
                has_order=Exists(
                    opqs
                ),
                has_cart=Exists(
                    cqs
                ),
                has_voucher=Exists(
                    vqs
                )
            )

        if minimal_distance > 0:
            # TODO: Is there a more performant implementation on PostgreSQL using
            # https://www.postgresql.org/docs/8.2/functions-geometry.html ?
            sq_closeby = qs_annotated.annotate(
                distance=(
                    Power(F('x') - OuterRef('x'), Value(2), output_field=models.FloatField()) +
                    Power(F('y') - OuterRef('y'), Value(2), output_field=models.FloatField())
                )
            ).filter(
                (
                    (Q(orderposition_id__isnull=False) | Q(cartposition_id__isnull=False) | Q(voucher_id__isnull=False))
                    if annotate_ids else
                    (Q(has_order=True) | Q(has_cart=True) | Q(has_voucher=True))
                ),
                distance__lt=minimal_distance ** 2
            )
            if distance_only_within_row:
                sq_closeby = sq_closeby.filter(row_name=OuterRef('row_name'))
            qs_annotated = qs_annotated.annotate(has_closeby_taken=Exists(sq_closeby))
        return qs_annotated

    def is_available(self, ignore_cart=None, ignore_orderpos=None, ignore_voucher_id=None,
                     sales_channel='web',
                     ignore_distancing=False, distance_ignore_cart_id=None):
        from .orders import Order
        from .organizer import SalesChannel

        if isinstance(sales_channel, SalesChannel):
            sales_channel = sales_channel.identifier
        if self.blocked and sales_channel not in self.event.settings.seating_allow_blocked_seats_for_channel:
            return False
        opqs = self.orderposition_set.filter(
            order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID],
            canceled=False
        )
        cpqs = self.cartposition_set.filter(expires__gte=now())
        vqs = self.vouchers.filter(
            Q(Q(valid_until__isnull=True) | Q(valid_until__gte=now())) &
            Q(redeemed__lt=F('max_usages'))
        )
        if ignore_cart and ignore_cart is not True:
            cpqs = cpqs.exclude(pk=ignore_cart.pk)
        if ignore_orderpos:
            opqs = opqs.exclude(pk=ignore_orderpos.pk)
        if ignore_voucher_id:
            vqs = vqs.exclude(pk=ignore_voucher_id)

        if opqs.exists() or (ignore_cart is not True and cpqs.exists()) or vqs.exists():
            return False

        if self.event.settings.seating_minimal_distance > 0 and not ignore_distancing:
            ev = (self.subevent or self.event)
            qs_annotated = Seat.annotated(ev.seats, self.event_id, self.subevent,
                                          ignore_voucher_id=ignore_voucher_id,
                                          minimal_distance=0,
                                          ignore_order_id=ignore_orderpos.order_id if ignore_orderpos else None,
                                          ignore_cart_id=(
                                              distance_ignore_cart_id or
                                              (ignore_cart.cart_id if ignore_cart and ignore_cart is not True else None)
                                          ))
            q = Q(has_order=True) | Q(has_voucher=True)
            if ignore_cart is not True:
                q |= Q(has_cart=True)

            # The following looks like it makes no sense. Why wouldn't we just use ``Value(self.x)``, we already now
            # the value? The reason is that x and y are floating point values generated from our JSON files. As it turns
            # out, PostgreSQL MIGHT store floating point values with a different precision based on the underlying system
            # architecture. So if we generate e.g. 670.247128887222289 from the JSON file and store it to the database,
            # PostgreSQL will store it as 670.247128887222289 internally. However if we query it again, we only get
            # 670.247128887222 back. But if we do calculations with a field in PostgreSQL itself, it uses the full
            # precision for the calculation.
            # We don't actually care about the results with this precision, but we care that the results from this
            # function are exactly the same as from event.free_seats(), so we do this subquery trick to deal with
            # PostgreSQL's internal values in both cases.
            # In the long run, we probably just want to round the numbers on insert...
            # See also https://www.postgresql.org/docs/11/runtime-config-client.html#GUC-EXTRA-FLOAT-DIGITS
            self_x = Subquery(Seat.objects.filter(pk=self.pk).values('x'))
            self_y = Subquery(Seat.objects.filter(pk=self.pk).values('y'))

            qs_closeby_taken = qs_annotated.annotate(
                distance=(
                    Power(F('x') - self_x, Value(2), output_field=models.FloatField()) +
                    Power(F('y') - self_y, Value(2), output_field=models.FloatField())
                )
            ).exclude(pk=self.pk).filter(
                q,
                distance__lt=self.event.settings.seating_minimal_distance ** 2
            )
            if self.event.settings.seating_distance_within_row:
                qs_closeby_taken = qs_closeby_taken.filter(row_name=self.row_name)
            if qs_closeby_taken.exists():
                return False

        return True
