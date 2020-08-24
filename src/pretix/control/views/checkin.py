import dateutil.parser
from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Subquery
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import is_aware, make_aware, now
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, ListView
from pytz import UTC

from pretix.base.channels import get_all_sales_channels
from pretix.base.models import Checkin, Order, OrderPosition
from pretix.base.models.checkin import CheckinList
from pretix.base.signals import checkin_created
from pretix.control.forms.checkin import CheckinListForm
from pretix.control.forms.filter import CheckInFilterForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, PaginationMixin, UpdateView


class CheckInListShow(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = Checkin
    context_object_name = 'entries'
    template_name = 'pretixcontrol/checkin/index.html'
    permission = 'can_view_orders'

    def get_queryset(self, filter=True):
        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=self.list.pk,
            type=Checkin.TYPE_ENTRY
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')
        cqs_exit = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=self.list.pk,
            type=Checkin.TYPE_EXIT
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')

        qs = OrderPosition.objects.filter(
            order__event=self.request.event,
            order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING] if self.list.include_pending else [Order.STATUS_PAID],
        ).annotate(
            last_entry=Subquery(cqs),
            last_exit=Subquery(cqs_exit),
            auto_checked_in=Exists(
                Checkin.objects.filter(position_id=OuterRef('pk'), list_id=self.list.pk, auto_checked_in=True)
            )
        ).select_related('item', 'variation', 'order', 'addon_to')
        if self.list.subevent:
            qs = qs.filter(
                subevent=self.list.subevent
            )

        if not self.list.all_products:
            qs = qs.filter(item__in=self.list.limit_products.values_list('id', flat=True))

        if filter and self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        return qs

    @cached_property
    def filter_form(self):
        return CheckInFilterForm(
            data=self.request.GET,
            event=self.request.event,
            list=self.list
        )

    def dispatch(self, request, *args, **kwargs):
        self.list = get_object_or_404(self.request.event.checkin_lists.all(), pk=kwargs.get("list"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['checkinlist'] = self.list
        if self.request.event.has_subevents:
            ctx['seats'] = (
                self.list.subevent.seating_plan_id if self.list.subevent
                else self.request.event.subevents.filter(seating_plan__isnull=False).exists()
            )
        else:
            ctx['seats'] = self.request.event.seating_plan_id
        ctx['filter_form'] = self.filter_form
        for e in ctx['entries']:
            if e.last_entry:
                if isinstance(e.last_entry, str):
                    # Apparently only happens on SQLite
                    e.last_entry_aware = make_aware(dateutil.parser.parse(e.last_entry), UTC)
                elif not is_aware(e.last_entry):
                    # Apparently only happens on MySQL
                    e.last_entry_aware = make_aware(e.last_entry, UTC)
                else:
                    # This would be correct, so guess on which database it works… Yes, it's PostgreSQL.
                    e.last_entry_aware = e.last_entry
            if e.last_exit:
                if isinstance(e.last_exit, str):
                    # Apparently only happens on SQLite
                    e.last_exit_aware = make_aware(dateutil.parser.parse(e.last_exit), UTC)
                elif not is_aware(e.last_exit):
                    # Apparently only happens on MySQL
                    e.last_exit_aware = make_aware(e.last_exit, UTC)
                else:
                    # This would be correct, so guess on which database it works… Yes, it's PostgreSQL.
                    e.last_exit_aware = e.last_exit
        return ctx

    def post(self, request, *args, **kwargs):
        if "can_change_orders" not in request.eventpermset:
            messages.error(request, _('You do not have permission to perform this action.'))
            return redirect(reverse('control:event.orders.checkins', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            }) + '?' + request.GET.urlencode())

        positions = self.get_queryset(filter=False).filter(
            pk__in=request.POST.getlist('checkin')
        )

        if request.POST.get('revert') == 'true':
            for op in positions:
                if op.order.status == Order.STATUS_PAID or (self.list.include_pending and op.order.status == Order.STATUS_PENDING):
                    Checkin.objects.filter(position=op, list=self.list).delete()
                    op.order.log_action('pretix.event.checkin.reverted', data={
                        'position': op.id,
                        'positionid': op.positionid,
                        'list': self.list.pk,
                        'web': True
                    }, user=request.user)
                    op.order.touch()

            messages.success(request, _('The selected check-ins have been reverted.'))
        else:
            for op in positions:
                if op.order.status == Order.STATUS_PAID or (self.list.include_pending and op.order.status == Order.STATUS_PENDING):
                    t = Checkin.TYPE_EXIT if request.POST.get('checkout') == 'true' else Checkin.TYPE_ENTRY

                    lci = op.checkins.filter(list=self.list).first()
                    if self.list.allow_multiple_entries or t != Checkin.TYPE_ENTRY or (lci and lci.type != Checkin.TYPE_ENTRY):
                        ci = Checkin.objects.create(position=op, list=self.list, datetime=now(), type=t)
                        created = True
                    else:
                        try:
                            ci, created = Checkin.objects.get_or_create(position=op, list=self.list, defaults={
                                'datetime': now(),
                            })
                        except Checkin.MultipleObjectsReturned:
                            ci, created = Checkin.objects.filter(position=op, list=self.list).first(), False

                    op.order.log_action('pretix.event.checkin', data={
                        'position': op.id,
                        'positionid': op.positionid,
                        'first': created,
                        'forced': False,
                        'datetime': now(),
                        'type': t,
                        'list': self.list.pk,
                        'web': True
                    }, user=request.user)
                    checkin_created.send(op.order.event, checkin=ci)

            messages.success(request, _('The selected tickets have been marked as checked in.'))

        return redirect(reverse('control:event.orders.checkinlists.show', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'list': self.list.pk
        }) + '?' + request.GET.urlencode())


class CheckinListList(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = CheckinList
    context_object_name = 'checkinlists'
    permission = 'can_view_orders'
    template_name = 'pretixcontrol/checkin/lists.html'

    def get_queryset(self):
        qs = self.request.event.checkin_lists.select_related('subevent').prefetch_related("limit_products")

        if self.request.GET.get("subevent", "") != "":
            s = self.request.GET.get("subevent", "")
            qs = qs.filter(subevent_id=s)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        clists = list(ctx['checkinlists'])
        sales_channels = get_all_sales_channels()

        for cl in clists:
            if cl.subevent:
                cl.subevent.event = self.request.event  # re-use same event object to make sure settings are cached
            cl.auto_checkin_sales_channels = [sales_channels[channel] for channel in cl.auto_checkin_sales_channels]
        ctx['checkinlists'] = clists

        ctx['can_change_organizer_settings'] = self.request.user.has_organizer_permission(
            self.request.organizer,
            'can_change_organizer_settings',
            self.request
        )

        return ctx


class CheckinListCreate(EventPermissionRequiredMixin, CreateView):
    model = CheckinList
    form_class = CheckinListForm
    template_name = 'pretixcontrol/checkin/list_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def dispatch(self, request, *args, **kwargs):
        r = super().dispatch(request, *args, **kwargs)
        r['Content-Security-Policy'] = 'script-src \'unsafe-eval\''
        return r

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


class CheckinListUpdate(EventPermissionRequiredMixin, UpdateView):
    model = CheckinList
    form_class = CheckinListForm
    template_name = 'pretixcontrol/checkin/list_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def dispatch(self, request, *args, **kwargs):
        r = super().dispatch(request, *args, **kwargs)
        r['Content-Security-Policy'] = 'script-src \'unsafe-eval\''
        return r

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
        self.object.checkins.all().delete()
        self.object.log_action(action='pretix.event.checkinlists.deleted', user=request.user)
        self.object.delete()
        messages.success(self.request, _('The selected list has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.checkinlists', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
