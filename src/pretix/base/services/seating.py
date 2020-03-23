from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _

from pretix.base.i18n import LazyLocaleException
from pretix.base.models import CartPosition, Seat


class SeatProtected(LazyLocaleException):
    def __init__(self, *args):
        msg = args[0]
        msgargs = args[1] if len(args) > 1 else None
        self.args = args
        if msgargs:
            msg = _(msg) % msgargs
        else:
            msg = _(msg)
        super().__init__(msg)


def validate_plan_change(event, subevent, plan):
    current_taken_seats = set(
        event.seats.select_related('product').annotate(
            has_op=Count('orderposition')
        ).annotate(has_v=Count('vouchers')).filter(
            subevent=subevent,
        ).filter(
            Q(has_v=True) | Q(has_op=True)
        ).values_list('seat_guid', flat=True).order_by()
    )
    new_seats = {
        ss.guid for ss in plan.iter_all_seats()
    } if plan else set()
    leftovers = list(current_taken_seats - new_seats)
    if leftovers:
        raise SeatProtected(_('You can not change the plan since seat "%s" is not present in the new plan and is '
                              'already sold.'), leftovers[0])


def generate_seats(event, subevent, plan, mapping):
    current_seats = {}
    for s in event.seats.select_related('product').annotate(
            has_op=Count('orderposition'), has_v=Count('vouchers')
    ).filter(subevent=subevent).order_by():
        if s.seat_guid in current_seats:
            s.delete()  # Duplicates should not exist
        else:
            current_seats[s.seat_guid] = s

    def update(o, a, v):
        if getattr(o, a) != v:
            setattr(o, a, v)
            return True
        return False

    create_seats = []
    if plan:
        for ss in plan.iter_all_seats():
            p = mapping.get(ss.category)
            if ss.guid in current_seats:
                seat = current_seats.pop(ss.guid)
                updated = any([
                    update(seat, 'product', p),
                    update(seat, 'name', ss.name),
                    update(seat, 'row_name', ss.row),
                    update(seat, 'seat_number', ss.number),
                    update(seat, 'zone_name', ss.zone),
                    update(seat, 'sorting_rank', ss.sorting_rank),
                    update(seat, 'row_label', ss.row_label),
                    update(seat, 'seat_label', ss.seat_label),
                ])
                if updated:
                    seat.save()
            else:
                create_seats.append(Seat(
                    event=event,
                    subevent=subevent,
                    seat_guid=ss.guid,
                    name=ss.name,
                    row_name=ss.row,
                    seat_number=ss.number,
                    zone_name=ss.zone,
                    sorting_rank=ss.sorting_rank,
                    row_label=ss.row_label,
                    seat_label=ss.seat_label,
                    product=p,
                ))

    for s in current_seats.values():
        if s.has_op:
            raise SeatProtected(_('You can not change the plan since seat "%s" is not present in the new plan and is '
                                  'already sold.', s.name))
        if s.has_v:
            raise SeatProtected(_('You can not change the plan since seat "%s" is not present in the new plan and is '
                                  'already used in a voucher.', s.name))

    Seat.objects.bulk_create(create_seats)
    CartPosition.objects.filter(seat__in=[s.pk for s in current_seats.values()]).delete()
    Seat.objects.filter(pk__in=[s.pk for s in current_seats.values()]).delete()
