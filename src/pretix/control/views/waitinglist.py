#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Daniel
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import csv
import io

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Max, Min, Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext
from django.views import View
from django.views.generic import ListView

from pretix.base.models import Item, Quota, WaitingListEntry
from pretix.base.models.waitinglist import WaitingListException
from pretix.base.services.waitinglist import assign_automatically
from pretix.base.views.tasks import AsyncAction
from pretix.control.forms.waitinglist import WaitingListEntryTransferForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import PaginationMixin

from ...helpers.compat import CompatDeleteView
from . import UpdateView


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


class WaitingListQuerySetMixin:

    @cached_property
    def request_data(self):
        if self.request.method == "POST":
            return self.request.POST
        return self.request.GET

    def get_queryset(self, force_filtered=False):
        qs = WaitingListEntry.objects.filter(
            event=self.request.event
        ).select_related('item', 'variation', 'voucher').prefetch_related(
            'item__quotas', 'variation__quotas'
        )

        s = self.request_data.get("status", "")
        if s == 's':
            qs = qs.filter(voucher__isnull=False)
        elif s == 'a':
            pass
        elif s == 'r':
            qs = qs.filter(
                voucher__isnull=False,
                voucher__redeemed__gte=F('voucher__max_usages'),
            )
        elif s == 'v':
            qs = qs.filter(
                voucher__isnull=False,
                voucher__redeemed__lt=F('voucher__max_usages'),
            ).filter(Q(voucher__valid_until__isnull=True) | Q(voucher__valid_until__gt=now()))
        elif s == 'e':
            qs = qs.filter(
                voucher__isnull=False,
                voucher__redeemed__lt=F('voucher__max_usages'),
                voucher__valid_until__isnull=False,
                voucher__valid_until__lte=now()
            )
        else:
            qs = qs.filter(voucher__isnull=True)

        if self.request_data.get("item", "") != "":
            i = self.request_data.get("item", "")
            qs = qs.filter(item_id=i)

        if self.request_data.get("subevent", "") != "":
            s = self.request_data.get("subevent", "")
            qs = qs.filter(subevent_id=s)

        if 'entry' in self.request_data and '__ALL' not in self.request_data:
            qs = qs.filter(
                id__in=self.request_data.getlist('entry')
            )
        elif force_filtered and '__ALL' not in self.request_data:
            qs = qs.none()

        return qs


class WaitingListActionView(EventPermissionRequiredMixin, WaitingListQuerySetMixin, View):
    model = WaitingListEntry
    permission = 'can_change_orders'

    def _redirect_back(self):
        if "next" in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next"), allowed_hosts=None):
            return redirect(self.request.GET.get("next"))
        return redirect(reverse('control:event.orders.waitinglist', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        }))

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete':
            return render(request, 'pretixcontrol/waitinglist/delete_bulk.html', {
                'allowed': self.get_queryset().filter(voucher__isnull=True),
                'forbidden': self.get_queryset().filter(voucher__isnull=False),
            })
        elif request.POST.get('action') == 'delete_confirm':
            for obj in self.get_queryset(force_filtered=True):
                if not obj.voucher_id:
                    obj.log_action('pretix.event.orders.waitinglist.deleted', user=self.request.user)
                    obj.delete()
            messages.success(request, _('The selected entries have been deleted.'))
            return self._redirect_back()

        if 'assign' in request.POST:
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
                return self._redirect_back()
            except WaitingListEntry.DoesNotExist:
                messages.error(request, _('Waiting list entry not found.'))
                return self._redirect_back()

        if 'move_top' in request.POST:
            try:
                wle = WaitingListEntry.objects.get(
                    pk=request.POST.get('move_top'), event=self.request.event,
                )
                wle.priority = self.request.event.waitinglistentries.aggregate(m=Max('priority'))['m'] + 1
                wle.save(update_fields=['priority'])
                wle.log_action(
                    'pretix.event.orders.waitinglist.changed',
                    data={'priority': wle.priority},
                    user=self.request.user,
                )
                messages.success(request, _('The waiting list entry has been moved to the top.'))
                return self._redirect_back()
            except WaitingListEntry.DoesNotExist:
                messages.error(request, _('Waiting list entry not found.'))
                return self._redirect_back()

        if 'move_end' in request.POST:
            try:
                wle = WaitingListEntry.objects.get(
                    pk=request.POST.get('move_end'), event=self.request.event,
                )
                wle.priority = self.request.event.waitinglistentries.aggregate(m=Min('priority'))['m'] - 1
                wle.save(update_fields=['priority'])
                wle.log_action(
                    'pretix.event.orders.waitinglist.changed',
                    data={'priority': wle.priority},
                    user=self.request.user,
                )
                messages.success(request, _('The waiting list entry has been moved to the end of the list.'))
                return self._redirect_back()
            except WaitingListEntry.DoesNotExist:
                messages.error(request, _('Waiting list entry not found.'))
                return self._redirect_back()
        return self._redirect_back()


class WaitingListView(EventPermissionRequiredMixin, WaitingListQuerySetMixin, PaginationMixin, ListView):
    model = WaitingListEntry
    context_object_name = 'entries'
    template_name = 'pretixcontrol/waitinglist/index.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = Item.objects.filter(event=self.request.event)
        ctx['filtered'] = ("status" in self.request.GET or "item" in self.request.GET)

        itemvar_cache = {}
        quota_cache = {}
        any_avail = False
        for wle in ctx[self.context_object_name]:
            if (wle.item, wle.variation, wle.subevent) in itemvar_cache:
                wle.availability = itemvar_cache.get((wle.item, wle.variation, wle.subevent))
            else:
                ev = (wle.subevent or self.request.event)
                disabled = (
                    not ev.presale_is_running or
                    (wle.subevent and not wle.subevent.active) or
                    not wle.item.is_available()
                )
                if disabled:
                    wle.availability = (0, "forbidden")
                else:
                    wle.availability = (
                        wle.variation.check_quotas(count_waitinglist=False, subevent=wle.subevent, _cache=quota_cache)
                        if wle.variation
                        else wle.item.check_quotas(count_waitinglist=False, subevent=wle.subevent, _cache=quota_cache)
                    )
                if wle.availability[0] == Quota.AVAILABILITY_OK and ev.seat_category_mappings.filter(product=wle.item).exists():
                    # See comment in WaitingListEntry.send_voucher() for rationale
                    num_free_seats_for_product = ev.free_seats().filter(product=wle.item).count()
                    num_valid_vouchers_for_product = self.request.event.vouchers.filter(
                        Q(valid_until__isnull=True) | Q(valid_until__gte=now()),
                        block_quota=True,
                        item_id=wle.item_id,
                        subevent=wle.subevent_id,
                        waitinglistentries__isnull=False
                    ).aggregate(free=Sum(F('max_usages') - F('redeemed')))['free'] or 0
                    free_seats = num_free_seats_for_product - num_valid_vouchers_for_product
                    wle.availability = (
                        Quota.AVAILABILITY_GONE if free_seats == 0 else wle.availability[0],
                        min(free_seats, wle.availability[1])
                    )

                itemvar_cache[(wle.item, wle.variation, wle.subevent)] = wle.availability
            if wle.availability[0] == Quota.AVAILABILITY_OK:
                any_avail = True

        ctx['any_avail'] = any_avail
        ctx['estimate'] = self.get_sales_estimate()

        ctx['running'] = (
            self.request.event.live
            and (self.request.event.has_subevents or self.request.event.presale_is_running)
        )

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

    def get(self, request, *args, **kwargs):
        if request.GET.get("download", "") == "yes":
            return self._download_csv()
        return super().get(request, *args, **kwargs)

    def _download_csv(self):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        headers = [
            _('Name'), _('E-mail address'), _('Phone number'), _('Product'), _('On list since'), _('Status'), _('Voucher code'),
            _('Language'), _('Priority')
        ]
        if self.request.event.has_subevents:
            headers.append(pgettext('subevent', 'Date'))
        writer.writerow(headers)

        for w in self.get_queryset():
            if w.item:
                if w.variation:
                    prod = '%s – %s' % (str(w.item), str(w.variation))
                else:
                    prod = '%s' % str(w.item)
            if w.voucher:
                if w.voucher.redeemed >= w.voucher.max_usages:
                    status = _('Voucher redeemed')
                elif not w.voucher.is_active():
                    status = _('Voucher expired')
                else:
                    status = _('Voucher assigned')
            else:
                status = _('Waiting')

            row = [
                w.name,
                w.email,
                w.phone,
                prod,
                w.created.isoformat(),
                status,
                w.voucher.code if w.voucher else '',
                w.locale,
                str(w.priority)
            ]
            if self.request.event.has_subevents:
                row.append(str(w.subevent))
            writer.writerow(row)

        r = HttpResponse(output.getvalue().encode("utf-8"), content_type='text/csv')
        r['Content-Disposition'] = 'attachment; filename="{}.csv"'.format(self.get_filename())
        return r

    def get_filename(self):
        return '{}_waitinglist'.format(self.request.event.slug)


class EntryDelete(EventPermissionRequiredMixin, CompatDeleteView):
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
        self.object.log_action('pretix.event.orders.waitinglist.deleted', user=self.request.user)
        self.object.delete()
        messages.success(self.request, _('The selected entry has been deleted.'))
        if "next" in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next"), allowed_hosts=None):
            return redirect(self.request.GET.get("next"))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.waitinglist', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })


class EntryTransfer(EventPermissionRequiredMixin, UpdateView):
    model = WaitingListEntry
    template_name = 'pretixcontrol/waitinglist/transfer.html'
    permission = 'can_change_orders'
    form_class = WaitingListEntryTransferForm
    context_object_name = 'entry'

    def dispatch(self, request, *args, **kwargs):
        if not self.request.event.has_subevents:
            raise Http404(_("This is not an event series."))
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None) -> WaitingListEntry:
        return get_object_or_404(WaitingListEntry, pk=self.kwargs['entry'], event=self.request.event, voucher__isnull=True)

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('The waitinglist entry has been transferred.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.orders.waitinglist.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.waitinglist', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })
