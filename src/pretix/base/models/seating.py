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
    RawSeat = namedtuple('Seat', 'name guid number row category zone')

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
        for z in self.layout_data['zones']:
            for r in z['rows']:
                for s in r['seats']:
                    yield self.RawSeat(
                        number=s['seat_number'],
                        guid=s['seat_guid'],
                        name='{} {}'.format(r['row_number'], s['seat_number']),  # TODO: Zone? Variable scheme?
                        row=r['row_number'],
                        zone=z['name'],
                        category=s['category']
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
    seat_number = models.CharField(max_length=190, blank=True, default="")
    seat_guid = models.CharField(max_length=190, db_index=True)
    product = models.ForeignKey('Item', null=True, blank=True, related_name='seats', on_delete=models.CASCADE)
    blocked = models.BooleanField(default=False)

    def __str__(self):
        parts = []
        if self.zone_name:
            parts.append(self.zone_name)
        if self.row_name:
            parts.append(gettext('Row {number}').format(number=self.row_name))
        if self.seat_number:
            parts.append(gettext('Seat {number}').format(number=self.seat_number))
        if not parts:
            return self.name
        return ', '.join(parts)

    def is_available(self, ignore_cart=None, ignore_orderpos=None, ignore_voucher_id=None):
        from .orders import Order

        if self.blocked:
            return False
        opqs = self.orderposition_set.filter(order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID])
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
