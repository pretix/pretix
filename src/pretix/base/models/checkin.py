from django.db import models
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, When
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_scopes import ScopedManager

from pretix.base.models import LoggedModel


class CheckinList(LoggedModel):
    event = models.ForeignKey('Event', related_name='checkin_lists', on_delete=models.CASCADE)
    name = models.CharField(max_length=190)
    all_products = models.BooleanField(default=True, verbose_name=_("All products (including newly created ones)"))
    limit_products = models.ManyToManyField('Item', verbose_name=_("Limit to products"), blank=True)
    subevent = models.ForeignKey('SubEvent', null=True, blank=True,
                                 verbose_name=pgettext_lazy('subevent', 'Date'), on_delete=models.CASCADE)
    include_pending = models.BooleanField(verbose_name=pgettext_lazy('checkin', 'Include pending orders'),
                                          default=False,
                                          help_text=_('With this option, people will be able to check in even if the '
                                                      'order have not been paid. This only works with pretixdesk '
                                                      '0.3.0 or newer or pretixdroid 1.9 or newer.'))

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        ordering = ('subevent__date_from', 'name')

    @staticmethod
    def annotate_with_numbers(qs, event):
        """
        Modifies a queryset of checkin lists by annotating it with the number of order positions and
        checkins associated with it.
        """
        # Import here to prevent circular import
        from . import Order, OrderPosition, Item

        # This is the mother of all subqueries. Sorry. I try to explain it, at least?
        # First, we prepare a subquery that for every check-in that belongs to a paid-order
        # position and to the list in question. Then, we check that it also belongs to the
        # correct subevent (just to be sure) and aggregate over lists (so, over everything,
        # since we filtered by lists).
        cqs_paid = Checkin.objects.filter(
            position__order__event=event,
            position__order__status=Order.STATUS_PAID,
            list=OuterRef('pk')
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(position__subevent=OuterRef('subevent'))
            | (Q(position__subevent__isnull=True))
        ).order_by().values('list').annotate(
            c=Count('*')
        ).values('c')
        cqs_paid_and_pending = Checkin.objects.filter(
            position__order__event=event,
            position__order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING],
            list=OuterRef('pk')
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(position__subevent=OuterRef('subevent'))
            | (Q(position__subevent__isnull=True))
        ).order_by().values('list').annotate(
            c=Count('*')
        ).values('c')

        # Now for the hard part: getting all order positions that contribute to this list. This
        # requires us to use TWO subqueries. The first one, pqs_all, will only be used for check-in
        # lists that contain all the products of the event. This is the simpler one, it basically
        # looks like the check-in counter above.
        pqs_all_paid = OrderPosition.objects.filter(
            order__event=event,
            order__status=Order.STATUS_PAID,
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(subevent=OuterRef('subevent'))
            | (Q(subevent__isnull=True))
        ).order_by().values('order__event').annotate(
            c=Count('*')
        ).values('c')
        pqs_all_paid_and_pending = OrderPosition.objects.filter(
            order__event=event,
            order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING]
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(subevent=OuterRef('subevent'))
            | (Q(subevent__isnull=True))
        ).order_by().values('order__event').annotate(
            c=Count('*')
        ).values('c')

        # Now we need a subquery for the case of checkin lists that are limited to certain
        # products. We cannot use OuterRef("limit_products") since that would do a cross-product
        # with the products table and we'd get duplicate rows in the output with different annotations
        # on them, which isn't useful at all. Therefore, we need to add a second layer of subqueries
        # to retrieve all of those items and then check if the item_id is IN this subquery result.
        pqs_limited_paid = OrderPosition.objects.filter(
            order__event=event,
            order__status=Order.STATUS_PAID,
            item_id__in=Subquery(Item.objects.filter(checkinlist__pk=OuterRef(OuterRef('pk'))).values('pk'))
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(subevent=OuterRef('subevent'))
            | (Q(subevent__isnull=True))
        ).order_by().values('order__event').annotate(
            c=Count('*')
        ).values('c')
        pqs_limited_paid_and_pending = OrderPosition.objects.filter(
            order__event=event,
            order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING],
            item_id__in=Subquery(Item.objects.filter(checkinlist__pk=OuterRef(OuterRef('pk'))).values('pk'))
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(subevent=OuterRef('subevent'))
            | (Q(subevent__isnull=True))
        ).order_by().values('order__event').annotate(
            c=Count('*')
        ).values('c')

        # Finally, we put all of this together. We force empty subquery aggregates to 0 by using Coalesce()
        # and decide which subquery to use for this row. In the end, we compute an integer percentage in case
        # we want to display a progress bar.
        return qs.annotate(
            checkin_count=Coalesce(
                Case(
                    When(include_pending=True, then=Subquery(cqs_paid_and_pending, output_field=models.IntegerField())),
                    default=Subquery(cqs_paid, output_field=models.IntegerField()),
                    output_field=models.IntegerField()
                ),
                0
            ),
            position_count=Coalesce(
                Case(
                    When(all_products=True, include_pending=False,
                         then=Subquery(pqs_all_paid, output_field=models.IntegerField())),
                    When(all_products=True, include_pending=True,
                         then=Subquery(pqs_all_paid_and_pending, output_field=models.IntegerField())),
                    When(all_products=False, include_pending=False,
                         then=Subquery(pqs_limited_paid, output_field=models.IntegerField())),
                    default=Subquery(pqs_limited_paid_and_pending, output_field=models.IntegerField()),
                    output_field=models.IntegerField()
                ),
                0
            )
        ).annotate(
            percent=Case(
                When(position_count__gt=0, then=F('checkin_count') * 100 / F('position_count')),
                default=0,
                output_field=models.IntegerField()
            )
        )

    def __str__(self):
        return self.name


class Checkin(models.Model):
    """
    A check-in object is created when a person enters the event.
    """
    position = models.ForeignKey('pretixbase.OrderPosition', related_name='checkins', on_delete=models.CASCADE)
    datetime = models.DateTimeField(default=now)
    nonce = models.CharField(max_length=190, null=True, blank=True)
    list = models.ForeignKey(
        'pretixbase.CheckinList', related_name='checkins', on_delete=models.PROTECT,
    )

    objects = ScopedManager(organizer='position__order__event__organizer')

    class Meta:
        unique_together = (('list', 'position'),)

    def __repr__(self):
        return "<Checkin: pos {} on list '{}' at {}>".format(
            self.position, self.list, self.datetime
        )

    def save(self, **kwargs):
        self.position.order.touch()
        super().save(**kwargs)

    def delete(self, **kwargs):
        self.position.order.touch()
        super().delete(**kwargs)
