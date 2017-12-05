from django.db import models
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, When
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _

from pretix.base.models import LoggedModel


class CheckinList(LoggedModel):
    event = models.ForeignKey('Event', related_name='checkin_lists')
    name = models.CharField(max_length=190)
    all_products = models.BooleanField(default=True, verbose_name=_("All products (including newly created ones)"))
    limit_products = models.ManyToManyField('Item', verbose_name=_("Limit to products"), blank=True)
    subevent = models.ForeignKey('SubEvent', null=True, blank=True,
                                 verbose_name=pgettext_lazy('subevent', 'Date'))

    @staticmethod
    def annotate_with_numbers(qs, event):
        from . import Order, OrderPosition
        cqs = Checkin.objects.filter(
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
        pqs_all = OrderPosition.objects.filter(
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
        pqs_limited = OrderPosition.objects.filter(
            order__event=event,
            order__status=Order.STATUS_PAID,
            item__in=OuterRef('limit_products')
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(subevent=OuterRef('subevent'))
            | (Q(subevent__isnull=True))
        ).order_by().values('order__event').annotate(
            c=Count('*')
        ).values('c')

        return qs.annotate(
            checkin_count=Coalesce(Subquery(cqs, output_field=models.IntegerField()), 0),
            position_count=Coalesce(Case(
                When(all_products=True, then=Subquery(pqs_all, output_field=models.IntegerField())),
                default=Subquery(pqs_limited, output_field=models.IntegerField()),
                output_field=models.IntegerField()
            ), 0)
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
    A checkin object is created when a person enters the event.
    """
    position = models.ForeignKey('pretixbase.OrderPosition', related_name='checkins')
    datetime = models.DateTimeField(default=now)
    nonce = models.CharField(max_length=190, null=True, blank=True)
    list = models.ForeignKey(
        'pretixbase.CheckinList', related_name='checkins', on_delete=models.PROTECT,
    )

    def __repr__(self):
        return "<Checkin: pos {} on list '{}' at {}>".format(
            self.position, self.list, self.datetime
        )
