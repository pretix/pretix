from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.views import View
from django.views.generic import ListView
from django.views.generic.edit import DeleteView

from pretix.base.models import Item, WaitingListEntry
from pretix.base.models.waitinglist import WaitingListException
from pretix.base.services.waitinglist import assign_automatically
from pretix.base.views.async import AsyncAction
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import PaginationMixin


class AutoAssign(EventPermissionRequiredMixin, AsyncAction, View):
    task = assign_automatically
    known_errortypes = ['WaitingListError']
    permission = 'can_change_orders'

    def get_success_message(self, value):
        return _('{num} vouchers have been created and sent out via email.').format(num=value)

    def get_success_url(self, value):
        return self.get_error_url()

    def get_error_url(self):
        return reverse('control:event.orders.waitinglist', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })

    def post(self, request, *args, **kwargs):
        return self.do(self.request.event.id, self.request.user.id,
                       self.request.POST.get('subevent'))


class WaitingListView(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = WaitingListEntry
    context_object_name = 'entries'
    template_name = 'pretixcontrol/waitinglist/index.html'
    permission = 'can_view_orders'

    def post(self, request, *args, **kwargs):
        if 'assign' in request.POST:
            if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders'):
                messages.error(request, _('You do not have permission to do this'))
                return redirect(reverse('control:event.orders.waitinglist', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug
                }))
            try:
                wle = WaitingListEntry.objects.get(
                    pk=request.POST.get('assign'), event=self.request.event,
                )
                try:
                    wle.send_voucher(user=request.user)
                except WaitingListException as e:
                    messages.error(request, str(e))
                else:
                    messages.success(request, _('An email containing a voucher code has been sent to the '
                                                'specified address.'))
                return redirect(reverse('control:event.orders.waitinglist', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug
                }))
            except WaitingListEntry.DoesNotExist:
                messages.error(request, _('Waiting list entry not found.'))
                return redirect(reverse('control:event.orders.waitinglist', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug
                }))

    def get_queryset(self):
        qs = WaitingListEntry.objects.filter(
            event=self.request.event
        ).select_related('item', 'variation', 'voucher').prefetch_related(
            'item__quotas', 'variation__quotas'
        )

        s = self.request.GET.get("status", "")
        if s == 's':
            qs = qs.filter(voucher__isnull=False)
        elif s == 'a':
            pass
        else:
            qs = qs.filter(voucher__isnull=True)

        if self.request.GET.get("item", "") != "":
            i = self.request.GET.get("item", "")
            qs = qs.filter(item_id=i)

        if self.request.GET.get("subevent", "") != "":
            s = self.request.GET.get("subevent", "")
            qs = qs.filter(subevent_id=s)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = Item.objects.filter(event=self.request.event)
        ctx['filtered'] = ("status" in self.request.GET or "item" in self.request.GET)

        itemvar_cache = {}
        quota_cache = {}
        any_avail = False
        for wle in ctx[self.context_object_name]:
            if (wle.item, wle.variation) in itemvar_cache:
                wle.availability = itemvar_cache.get((wle.item, wle.variation))
            else:
                wle.availability = (
                    wle.variation.check_quotas(count_waitinglist=False, subevent=wle.subevent, _cache=quota_cache)
                    if wle.variation
                    else wle.item.check_quotas(count_waitinglist=False, subevent=wle.subevent, _cache=quota_cache)
                )
                itemvar_cache[(wle.item, wle.variation)] = wle.availability
            if wle.availability[0] == 100:
                any_avail = True

        ctx['any_avail'] = any_avail
        ctx['estimate'] = self.get_sales_estimate()
        return ctx

    def get_sales_estimate(self):
        qs = WaitingListEntry.objects.filter(
            event=self.request.event, voucher__isnull=True
        ).aggregate(
            s=Sum(
                Coalesce('variation__default_price', 'item__default_price')
            )
        )
        return qs['s']


class EntryDelete(EventPermissionRequiredMixin, DeleteView):
    model = WaitingListEntry
    template_name = 'pretixcontrol/waitinglist/delete.html'
    permission = 'can_change_orders'
    context_object_name = 'entry'

    def get_object(self, queryset=None) -> WaitingListEntry:
        try:
            return self.request.event.waitinglistentries.get(
                id=self.kwargs['entry'],
                voucher__isnull=True,
            )
        except WaitingListEntry.DoesNotExist:
            raise Http404(_("The requested entry does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.log_action('pretix.event.orders.waitinglist.delete', user=self.request.user)
        self.object.delete()
        messages.success(self.request, _('The selected entry has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.waitinglist', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })
