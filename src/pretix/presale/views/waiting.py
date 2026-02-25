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
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views.generic import FormView, TemplateView, View

from pretix.base.models import Quota, SubEvent
from pretix.base.templatetags.urlreplace import url_replace
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin, iframe_entry_view_wrapper
from pretix.presale.views.customer import CustomerRequiredMixin

from ...base.i18n import get_language_without_region
from ...base.models import Voucher, WaitingListEntry
from ..forms.waitinglist import WaitingListForm
from . import allow_frame_if_namespaced


def get_waiting_list_ranks(event, customer_email):
    """
    Get waiting list ranks for a customer.
    
    Returns a list of product data dictionaries with rank information.
    Each dictionary contains: item_id, item_name, variation_id, variation_name, rank, lottery_run, 
    and optionally voucher_code, voucher_expired, and voucher_expired_date.
    """
    entries = WaitingListEntry.objects.filter(
        event=event,
        email__iexact=customer_email
    ).select_related('item', 'variation', 'voucher').order_by('item', 'variation', '-created', '-pk')
    
    # Group entries by product (item + variation combination)
    products_data = []
    seen_products = set()
    
    for entry in entries:
        # Create a unique key for this product (item + variation)
        product_key = (entry.item_id, entry.variation_id if entry.variation else None)
        
        # Only process the most recent entry for each product
        if product_key in seen_products:
            continue
        
        seen_products.add(product_key)
        
        rank = entry.get_rank()
        
        # Check if this is an expired voucher (rank is None but voucher exists and is expired)
        voucher_expired = False
        voucher_expired_date = None
        if rank is None and entry.voucher and not entry.voucher.is_active():
            # Check if voucher expired (not just fully redeemed)
            if entry.voucher.valid_until and entry.voucher.valid_until < now():
                voucher_expired = True
                # Convert to event timezone for display
                tz = ZoneInfo(event.settings.timezone)
                voucher_expired_date = entry.voucher.valid_until.astimezone(tz)
        
        # Skip entries that are no longer active (rank is None) unless they have expired vouchers
        if rank is None and not voucher_expired:
            continue
        
        # Check if lottery has been run for this product
        lottery_date = event.settings.get(f'lottery_date_for_item_{entry.item_id}')
        lottery_run = bool(lottery_date)
        
        product_data = {
            'item_id': entry.item_id,
            'item_name': str(entry.item),
            'variation_id': entry.variation_id,
            'variation_name': str(entry.variation) if entry.variation else None,
            'rank': rank,
            'lottery_run': lottery_run
        }
        
        # Include voucher code if rank is 0 (user has an unredeemed voucher)
        if rank == 0 and entry.voucher:
            product_data['voucher_code'] = entry.voucher.code
        
        # Include expired voucher information
        if voucher_expired:
            product_data['voucher_expired'] = True
            product_data['voucher_expired_date'] = voucher_expired_date
        
        products_data.append(product_data)
    
    return products_data


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class WaitingView(EventViewMixin, CustomerRequiredMixin, FormView):
    template_name = 'pretixpresale/event/waitinglist.html'
    form_class = WaitingListForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        kwargs['event'] = self.request.event
        kwargs['instance'] = WaitingListEntry(
            event=self.request.event, locale=get_language_without_region(),
            subevent=self.subevent
        )
        kwargs['channel'] = self.request.sales_channel.identifier
        kwargs['customer'] = getattr(self.request, 'customer', None)
        kwargs.setdefault('initial', {})
        if 'var' in self.request.GET:
            kwargs['initial']['itemvar'] = f'{self.request.GET.get("item")}-{self.request.GET.get("var")}'
        else:
            kwargs['initial']['itemvar'] = self.request.GET.get("item")
        if getattr(self.request, 'customer', None):
            kwargs['initial']['email'] = self.request.customer.email
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.request.event
        ctx['subevent'] = self.subevent
        return ctx

    def get(self, request, *args, **kwargs):
        if request.GET.get('iframe', '') == '1' and 'require_cookie' not in request.GET:
            # Widget just opened. Let's to a stupid redirect to check if cookies are disabled
            return redirect(request.get_full_path() + '&require_cookie=true')
        elif 'require_cookie' in request.GET and settings.SESSION_COOKIE_NAME not in request.COOKIES:
            # Cookies are in fact not supported. We can't even display the form, since we can't get CSRF right without
            # cookies.
            r = render(request, 'pretixpresale/event/cookies.html', {
                'url': eventreverse(
                    request.event, "presale:event.waitinglist", kwargs={'cart_namespace': kwargs.get('cart_namespace')}
                ) + '?' + url_replace(request, 'require_cookie', '', 'iframe', '', 'locale', request.GET.get('locale', get_language_without_region()))
            })
            r._csp_ignore = True
            return r

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        if not self.request.event.settings.waiting_list_enabled:
            messages.error(request, _("Waiting lists are disabled for this event."))
            return redirect(self.get_index_url())

        if self.request.event.presale_has_ended:
            messages.error(request, _("The booking period for this event is over."))
            return redirect(self.get_index_url())

        if not self.request.event.presale_is_running:
            messages.error(request, _("The booking period for this event has not yet started."))
            return redirect(self.get_index_url())

        self.subevent = None
        if request.event.has_subevents:
            if 'subevent' in request.GET:
                self.subevent = get_object_or_404(SubEvent, event=request.event, pk=request.GET['subevent'],
                                                  active=True)
            else:
                messages.error(request, pgettext_lazy('subevent', "You need to select a date."))
                return redirect(self.get_index_url())

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        availability = (
            form.instance.variation.check_quotas(count_waitinglist=True, subevent=self.subevent)
            if form.instance.variation
            else form.instance.item.check_quotas(count_waitinglist=True, subevent=self.subevent)
        )
        if availability[0] == Quota.AVAILABILITY_OK:
            messages.error(self.request, _("You cannot add yourself to the waiting list as this product is currently "
                                           "available."))
            return redirect(self.get_index_url())

        form.save()
        form.instance.send_confirm()

        form.instance.log_action("pretix.event.orders.waitinglist.added")
        messages.success(self.request, _("We've added you to the waiting list. You will receive "
                                         "an email when a ticket is available."))

        return super().form_valid(form)

    def get_success_url(self):
        return self.get_index_url()


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class WaitingRemoveView(EventViewMixin, CustomerRequiredMixin, TemplateView):
    template_name = 'pretixpresale/event/waitinglist_remove.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.request.event
        ctx['voucher'] = self.voucher
        return ctx

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        try:
            self.voucher = self.request.event.vouchers.get(
                code=request.GET.get("voucher", ""),
                waitinglistentries__isnull=False,
            )
        except Voucher.DoesNotExist:
            messages.error(request, _("We could not find you on our waiting list."))
            return redirect(self.get_index_url())

        if not self.voucher.is_active():
            messages.error(request, _("Your waiting list spot is no longer valid or already used. There's nothing more to do here."))
            return redirect(self.get_index_url())

        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        self.voucher.valid_until = now() - timedelta(seconds=1)
        self.voucher.save(update_fields=['valid_until'])
        self.voucher.log_action('pretix.voucher.expired.waitinglist')
        messages.success(request, _("Thank you very much! We will assign your spot on the waiting list to someone else."))
        return redirect(self.get_index_url())

    def get_success_url(self):
        return self.get_index_url()
