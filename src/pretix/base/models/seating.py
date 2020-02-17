import json
from collections import namedtuple

import jsonschema
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils.deconstruct import deconstructible
from django.utils.timezone import now
from django.utils.translation import gettext, ugettext_lazy as _

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
            raise ValidationError(_('Your layout file is not a valid seating plan. Error message: {}').format(str(e)))


class SeatingPlan(LoggedModel):
    """
    Represents an abstract seating plan, without relation to any event.
    """
    name = models.CharField(max_length=190, verbose_name=_('Name'))
    organizer = models.ForeignKey(Organizer, related_name='seating_plans', on_delete=models.CASCADE)
    layout = models.TextField(validators=[SeatingPlanLayoutValidator()])

    Category = namedtuple('Categrory', 'name')
    RawSeat = namedtuple('Seat', 'name guid number row category zone sorting_rank row_label seat_label')

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
            for ri, r in enumerate(z['rows']):
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
                        name='{} {}'.format(r['row_number'], s['seat_number']),  # TODO: Zone? Variable scheme?
                        row=r['row_number'],
                        row_label=row_label,
                        seat_label=seat_label,
                        zone=z['name'],
                        category=s['category'],
                        sorting_rank=rank
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
    name = models.CharField(max_length=190)
    zone_name = models.CharField(max_length=190, blank=True, default="")
    row_name = models.CharField(max_length=190, blank=True, default="")
    row_label = models.CharField(max_length=190, null=True)
    seat_number = models.CharField(max_length=190, blank=True, default="")
    seat_label = models.CharField(max_length=190, null=True)
    seat_guid = models.CharField(max_length=190, db_index=True)
    product = models.ForeignKey('Item', null=True, blank=True, related_name='seats', on_delete=models.CASCADE)
    blocked = models.BooleanField(default=False)
    sorting_rank = models.BigIntegerField(default=0)

    class Meta:
        ordering = ['sorting_rank', 'seat_guid']

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
            return self.name
        return ', '.join(parts)

    def is_available(self, ignore_cart=None, ignore_orderpos=None, ignore_voucher_id=None, sales_channel='web'):
        from .orders import Order

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
        return not opqs.exists() and (ignore_cart is True or not cpqs.exists()) and not vqs.exists()
