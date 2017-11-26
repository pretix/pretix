from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import models, transaction
from django.db.models import Count, F, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DeleteView, ListView

from pretix.base.models import Checkin, Item, Order, OrderPosition
from pretix.base.models.checkin import CheckinList
from pretix.control.forms.checkin import CheckinListForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, UpdateView


class CheckInView(EventPermissionRequiredMixin, ListView):
    model = Checkin
    context_object_name = 'entries'
    paginate_by = 30
    template_name = 'pretixcontrol/checkin/index.html'
    permission = 'can_view_orders'

    def get_queryset(self):

        qs = OrderPosition.objects.filter(order__event=self.request.event, order__status='p')

        # if this setting is False, we check only items for admission
        if not self.request.event.settings.ticket_download_nonadm:
            qs = qs.filter(item__admission=True)

        if self.request.GET.get("status", "") != "":
            p = self.request.GET.get("status", "")
            if p == '1':
                # records with check-in record
                qs = qs.filter(checkins__isnull=False)
            elif p == '0':
                qs = qs.filter(checkins__isnull=True)

        if self.request.GET.get("user", "") != "":
            u = self.request.GET.get("user", "")
            qs = qs.filter(
                Q(order__email__icontains=u) | Q(attendee_name__icontains=u) | Q(attendee_email__icontains=u)
            )

        if self.request.GET.get("item", "") != "":
            u = self.request.GET.get("item", "")
            qs = qs.filter(item_id=u)

        if self.request.GET.get("subevent", "") != "":
            s = self.request.GET.get("subevent", "")
            qs = qs.filter(subevent_id=s)

        qs = qs.prefetch_related(
            Prefetch('checkins', queryset=Checkin.objects.filter(position__order__event=self.request.event))
        ).select_related('order', 'item', 'addon_to')

        if self.request.GET.get("ordering", "") != "":
            p = self.request.GET.get("ordering", "")
            keys_allowed = self.get_ordering_keys_mappings()
            if p in keys_allowed:
                mapped_field = keys_allowed[p]
                if isinstance(mapped_field, dict):
                    order = mapped_field.pop('_order')
                    qs = qs.annotate(**mapped_field).order_by(order)
                elif isinstance(mapped_field, (list, tuple)):
                    qs = qs.order_by(*mapped_field)
                else:
                    qs = qs.order_by(mapped_field)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = Item.objects.filter(event=self.request.event)
        ctx['filtered'] = ("status" in self.request.GET or "user" in self.request.GET or "item" in self.request.GET
                           or "subevent" in self.request.GET)
        return ctx

    def post(self, request, *args, **kwargs):
        positions = OrderPosition.objects.select_related('item', 'variation', 'order', 'addon_to').filter(
            order__event=self.request.event,
            pk__in=request.POST.getlist('checkin')
        )

        for op in positions:
            created = False
            if op.order.status == Order.STATUS_PAID:
                ci, created = Checkin.objects.get_or_create(position=op, defaults={
                    'datetime': now(),
                })
            op.order.log_action('pretix.control.views.checkin', data={
                'position': op.id,
                'positionid': op.positionid,
                'first': created,
                'datetime': now()
            }, user=request.user)

        messages.success(request, _('The selected tickets have been marked as checked in.'))
        return redirect(reverse('control:event.orders.checkins', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        }) + '?' + request.GET.urlencode())

    @staticmethod
    def get_ordering_keys_mappings():
        return {
            'code': 'order__code',
            '-code': '-order__code',
            'email': 'order__email',
            '-email': '-order__email',
            # Set nulls_first to be consistent over databases
            'status': F('checkins__id').asc(nulls_first=True),
            '-status': F('checkins__id').desc(nulls_last=True),
            'timestamp': F('checkins__datetime').asc(nulls_first=True),
            '-timestamp': F('checkins__datetime').desc(nulls_last=True),
            'item': ('item__name', 'variation__value'),
            '-item': ('-item__name', 'variation__value'),
            'subevent': ('subevent__date_from', 'subevent__name'),
            '-subevent': ('-subevent__date_from', '-subevent__name'),
            'name': {'_order': F('display_name').asc(nulls_first=True),
                     'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')},
            '-name': {'_order': F('display_name').desc(nulls_last=True),
                      'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')},
        }


class CheckinListList(ListView):
    model = CheckinList
    context_object_name = 'checkinlists'
    paginate_by = 30
    permission = 'can_view_orders'
    template_name = 'pretixcontrol/checkin/lists.html'

    def get_queryset(self):
        cqs = Checkin.objects.filter(
            position__order__event=self.request.event,
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
        pqs = OrderPosition.objects.filter(
            order__event=self.request.event,
            order__status=Order.STATUS_PAID,
        ).filter(
            # This assumes that in an event with subevents, *all* positions have subevents
            # and *all* checkin lists have a subevent assigned
            Q(subevent=OuterRef('subevent'))
            | (Q(subevent__isnull=True))
        ).order_by().values('order__event').annotate(
            c=Count('*')
        ).values('c')
        # TODO: Limit products

        # if not self.config.list.all_products:
        #    pqs = pqs.filter(item__in=self.config.list.limit_products.values_list('id', flat=True))

        qs = self.request.event.checkin_lists.prefetch_related("limit_products").annotate(
            checkin_count=Subquery(cqs, output_field=models.IntegerField()),
            position_count=Subquery(pqs, output_field=models.IntegerField())
        ).annotate(
            percent=F('checkin_count') * 100 / F('position_count')
        )

        if self.request.GET.get("subevent", "") != "":
            s = self.request.GET.get("subevent", "")
            qs = qs.filter(subevent_id=s)
        return qs


class CheckinListCreate(EventPermissionRequiredMixin, CreateView):
    model = CheckinList
    form_class = CheckinListForm
    template_name = 'pretixcontrol/checkin/list_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def get_success_url(self) -> str:
        return reverse('control:event.orders.checkinlists', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new check-in list has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.checkinlist.added', user=self.request.user,
                                 data=dict(form.cleaned_data))
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


"""
class QuotaView(ChartContainingView, DetailView):
    model = Quota
    template_name = 'pretixcontrol/items/quota.html'
    context_object_name = 'quota'

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data()

        avail = self.object.availability()
        ctx['avail'] = avail

        data = [
            {
                'label': ugettext('Paid orders'),
                'value': self.object.count_paid_orders(),
                'sum': True,
            },
            {
                'label': ugettext('Pending orders'),
                'value': self.object.count_pending_orders(),
                'sum': True,
            },
            {
                'label': ugettext('Vouchers'),
                'value': self.object.count_blocking_vouchers(),
                'sum': True,
            },
            {
                'label': ugettext('Current user\'s carts'),
                'value': self.object.count_in_cart(),
                'sum': True,
            },
            {
                'label': ugettext('Waiting list'),
                'value': self.object.count_waiting_list_pending(),
                'sum': False,
            },
        ]
        ctx['quota_table_rows'] = list(data)

        sum_values = sum([d['value'] for d in data if d['sum']])

        if self.object.size is not None:
            data.append({
                'label': ugettext('Current availability'),
                'value': avail[1]
            })

        ctx['quota_chart_data'] = json.dumps(data)
        ctx['quota_overbooked'] = sum_values - self.object.size if self.object.size is not None else 0

        ctx['has_ignore_vouchers'] = Voucher.objects.filter(
            Q(allow_ignore_quota=True) &
            Q(Q(valid_until__isnull=True) | Q(valid_until__gte=now())) &
            Q(Q(self.object._position_lookup) | Q(quota=self.object)) &
            Q(redeemed__lt=F('max_usages'))
        ).exists()

        return ctx

    def get_object(self, queryset=None) -> Quota:
        try:
            return self.request.event.quotas.get(
                id=self.kwargs['quota']
            )
        except Quota.DoesNotExist:
            raise Http404(_("The requested quota does not exist."))
"""


class CheckinListUpdate(EventPermissionRequiredMixin, UpdateView):
    model = CheckinList
    form_class = CheckinListForm
    template_name = 'pretixcontrol/checkin/list_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def get_object(self, queryset=None) -> CheckinList:
        try:
            return self.request.event.checkin_lists.get(
                id=self.kwargs['list']
            )
        except CheckinList.DoesNotExist:
            raise Http404(_("The requested list does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.checkinlist.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.checkinlists.show', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'list': self.object.pk
        })

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class CheckinListDelete(EventPermissionRequiredMixin, DeleteView):
    model = CheckinList
    template_name = 'pretixcontrol/checkin/list_delete.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def get_object(self, queryset=None) -> CheckinList:
        try:
            return self.request.event.checkin_lists.get(
                id=self.kwargs['list']
            )
        except CheckinList.DoesNotExist:
            raise Http404(_("The requested list does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.log_action(action='pretix.event.orders.deleted', user=request.user)
        self.object.delete()
        messages.success(self.request, _('The selected list has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.checkinlists', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
