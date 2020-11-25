from django.conf import settings
from django.db import models
from django.db.models import Exists, F, Max, OuterRef, Q, Subquery
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager, scopes_disabled
from jsonfallback.fields import FallbackJSONField

from pretix.base.models import LoggedModel
from pretix.base.models.fields import MultiStringField


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
                                                      'order has not been paid.'))
    gates = models.ManyToManyField(
        'Gate', verbose_name=_("Gates"), blank=True,
        help_text=_("Does not have any effect for the validation of tickets, only for the automatic configuration of "
                    "check-in devices.")
    )
    allow_entry_after_exit = models.BooleanField(
        verbose_name=_('Allow re-entering after an exit scan'),
        default=True
    )
    allow_multiple_entries = models.BooleanField(
        verbose_name=_('Allow multiple entries per ticket'),
        help_text=_('Use this option to turn off warnings if a ticket is scanned a second time.'),
        default=False
    )
    exit_all_at = models.DateTimeField(
        verbose_name=_('Automatically check out everyone at'),
        null=True, blank=True
    )
    auto_checkin_sales_channels = MultiStringField(
        default=[],
        blank=True,
        verbose_name=_('Sales channels to automatically check in'),
        help_text=_('All items on this check-in list will be automatically marked as checked-in when purchased through '
                    'any of the selected sales channels. This option can be useful when tickets sold at the box office '
                    'are not checked again before entry and should be considered validated directly upon purchase.')
    )
    rules = FallbackJSONField(default=dict, blank=True)

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        ordering = ('subevent__date_from', 'name')

    @property
    def positions(self):
        from . import Order, OrderPosition

        qs = OrderPosition.objects.filter(
            order__event=self.event,
            order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING] if self.include_pending else [
                Order.STATUS_PAID],
        )
        if self.subevent_id:
            qs = qs.filter(subevent_id=self.subevent_id)
        if not self.all_products:
            qs = qs.filter(item__in=self.limit_products.values_list('id', flat=True))
        return qs

    @property
    def positions_inside(self):
        return self.positions.annotate(
            last_entry=Subquery(
                Checkin.objects.filter(
                    position_id=OuterRef('pk'),
                    list_id=self.pk,
                    type=Checkin.TYPE_ENTRY,
                ).order_by().values('position_id').annotate(
                    m=Max('datetime')
                ).values('m')
            ),
            last_exit=Subquery(
                Checkin.objects.filter(
                    position_id=OuterRef('pk'),
                    list_id=self.pk,
                    type=Checkin.TYPE_EXIT,
                ).order_by().values('position_id').annotate(
                    m=Max('datetime')
                ).values('m')
            ),
        ).filter(
            Q(last_entry__isnull=False)
            & Q(
                Q(last_exit__isnull=True) | Q(last_exit__lt=F('last_entry'))
            )
        )

    @property
    def inside_count(self):
        return self.positions_inside.count()

    @property
    @scopes_disabled()
    # Disable scopes, because this query is safe and the additional organizer filter in the EXISTS() subquery tricks PostgreSQL into a bad
    # subplan that sequentially scans all events
    def checkin_count(self):
        return self.event.cache.get_or_set(
            'checkin_list_{}_checkin_count'.format(self.pk),
            lambda: self.positions.using(settings.DATABASE_REPLICA).annotate(
                checkedin=Exists(Checkin.objects.filter(list_id=self.pk, position=OuterRef('pk'), type=Checkin.TYPE_ENTRY,))
            ).filter(
                checkedin=True
            ).count(),
            60
        )

    @property
    def percent(self):
        pc = self.position_count
        return round(self.checkin_count * 100 / pc) if pc else 0

    @property
    def position_count(self):
        return self.event.cache.get_or_set(
            'checkin_list_{}_position_count'.format(self.pk),
            lambda: self.positions.count(),
            60
        )

    def touch(self):
        self.event.cache.delete('checkin_list_{}_position_count'.format(self.pk))
        self.event.cache.delete('checkin_list_{}_checkin_count'.format(self.pk))

    @staticmethod
    def annotate_with_numbers(qs, event):
        # This is only kept for backwards-compatibility reasons. This method used to precompute .position_count
        # and .checkin_count through a huge subquery chain, but was dropped for performance reasons.
        return qs

    def __str__(self):
        return self.name


class Checkin(models.Model):
    """
    A check-in object is created when a person enters or exits the event.
    """
    TYPE_ENTRY = 'entry'
    TYPE_EXIT = 'exit'
    CHECKIN_TYPES = (
        (TYPE_ENTRY, _('Entry')),
        (TYPE_EXIT, _('Exit')),
    )
    position = models.ForeignKey('pretixbase.OrderPosition', related_name='checkins', on_delete=models.CASCADE)
    datetime = models.DateTimeField(default=now)
    nonce = models.CharField(max_length=190, null=True, blank=True)
    list = models.ForeignKey(
        'pretixbase.CheckinList', related_name='checkins', on_delete=models.PROTECT,
    )
    type = models.CharField(max_length=100, choices=CHECKIN_TYPES, default=TYPE_ENTRY)
    forced = models.BooleanField(default=False)
    device = models.ForeignKey(
        'pretixbase.Device', related_name='checkins', on_delete=models.PROTECT, null=True, blank=True
    )
    gate = models.ForeignKey(
        'pretixbase.Gate', related_name='checkins', on_delete=models.SET_NULL, null=True, blank=True
    )
    auto_checked_in = models.BooleanField(default=False)

    objects = ScopedManager(organizer='position__order__event__organizer')

    class Meta:
        ordering = (('-datetime'),)

    def __repr__(self):
        return "<Checkin: pos {} on list '{}' at {}>".format(
            self.position, self.list, self.datetime
        )

    def save(self, **kwargs):
        super().save(**kwargs)
        self.position.order.touch()
        self.list.event.cache.delete('checkin_count')
        self.list.touch()

    def delete(self, **kwargs):
        super().delete(**kwargs)
        self.position.order.touch()
        self.list.touch()
