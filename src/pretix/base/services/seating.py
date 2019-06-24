from django.db.models import Count
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import CartPosition, Seat


class SeatProtected(Exception):
    pass


def validate_plan_change(event, subevent, plan):
    current_taken_seats = set(
        event.seats.select_related('product')
             .annotate(has_op=Count('orderposition'))
             .filter(subevent=subevent, has_op=True)
             .values_list('seat_guid', flat=True)
    )
    new_seats = {
        ss.guid for ss in plan.iter_all_seats()
    } if plan else set()
    leftovers = list(current_taken_seats - new_seats)
    if leftovers:
        raise SeatProtected(_('You can not change the plan since seat "{}" is not present in the new plan and is '
                              'already sold.').format(leftovers[0]))


def generate_seats(event, subevent, plan, mapping):
    current_seats = {
        s.seat_guid: s for s in
        event.seats.select_related('product').annotate(has_op=Count('orderposition')).filter(subevent=subevent)
    }
    create_seats = []
    if plan:
        for ss in plan.iter_all_seats():
            p = mapping.get(ss.category)
            if ss.guid in current_seats:
                seat = current_seats.pop(ss.guid)
                if seat.product != p:
                    seat.product = p
                    seat.save()
            else:
                create_seats.append(Seat(
                    event=event,
                    subevent=subevent,
                    seat_guid=ss.guid,
                    name=ss.name,
                    product=p,
                ))

    for s in current_seats.values():
        if s.has_op:
            raise SeatProtected(_('You can not change the plan since seat "{}" is not present in the new plan and is '
                                  'already sold.').format(s.name))

    Seat.objects.bulk_create(create_seats)
    CartPosition.objects.filter(seat__in=[s.pk for s in current_seats.values()]).delete()
    Seat.objects.filter(pk__in=[s.pk for s in current_seats.values()]).delete()
