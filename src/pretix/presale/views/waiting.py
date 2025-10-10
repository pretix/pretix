#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views.generic import FormView, TemplateView

from pretix.base.models import Quota, SubEvent
from pretix.base.templatetags.urlreplace import url_replace
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin, iframe_entry_view_wrapper

from ...base.i18n import get_language_without_region
from ...base.models import Voucher, WaitingListEntry
from ..forms.waitinglist import WaitingListForm
from . import allow_frame_if_namespaced
from .event import get_grouped_items


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class WaitingView(EventViewMixin, FormView):
    template_name = 'pretixpresale/event/waitinglist.html'
    form_class = WaitingListForm

    @cached_property
    def itemvars(self):
        customer = getattr(self.request, 'customer', None)
        items, display_add_to_cart = get_grouped_items(
            self.request.event,
            subevent=self.subevent,
            require_seat=None,
            channel=self.request.organizer.sales_channels.get(identifier="web"),
            memberships=(
                customer.usable_memberships(
                    for_event=self.subevent or self.request.event,
                    testmode=self.request.event.testmode
                )
                if customer else None
            ),
        )
        choices = []
        for i in items:
            if not i.allow_waitinglist:
                continue

            if i.has_variations:
                for v in i.available_variations:
                    if v.cached_availability[0] == Quota.AVAILABILITY_OK:
                        continue
                    choices.append((f'{i.pk}-{v.pk}', f'{i.name} – {v.value}'))

            else:
                if i.cached_availability[0] == Quota.AVAILABILITY_OK:
                    continue
                choices.append((f'{i.pk}', f'{i.name}'))
        return choices

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        kwargs['event'] = self.request.event
        kwargs['instance'] = WaitingListEntry(
            event=self.request.event, locale=get_language_without_region(),
            subevent=self.subevent
        )
        kwargs['itemvars'] = self.itemvars
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
        elif 'require_cookie' in request.GET and settings.SESSION_COOKIE_NAME not in request.COOKIES and\
                '__Host-' + settings.SESSION_COOKIE_NAME not in self.request.COOKIES:
            # Cookies are in fact not supported. We can't even display the form, since we can't get CSRF right without
            # cookies.
            r = render(request, 'pretixpresale/event/cookies.html', {
                'url': eventreverse(
                    request.event, "presale:event.waitinglist", kwargs={'cart_namespace': kwargs.get('cart_namespace')}
                ) + '?' + url_replace(request, 'require_cookie', '', 'iframe', '', 'locale', request.GET.get('locale', get_language_without_region()))
            })
            r._csp_ignore = True
            return r

        if not self.itemvars:
            messages.info(request, _("No ticket types are available for the waiting list, have a look at the "
                                     "ticket shop instead."))
            return redirect(self.get_index_url())

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
                try:
                    self.subevent = get_object_or_404(SubEvent, event=request.event, pk=request.GET['subevent'],
                                                      active=True)
                except ValueError:
                    raise Http404()
            else:
                messages.error(request, pgettext_lazy('subevent', "You need to select a date."))
                return redirect(self.get_index_url())

        if not (self.subevent or self.request.event).waiting_list_active:
            messages.error(request, _("Waiting lists are disabled for this event."))
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
        form.instance.log_action("pretix.event.orders.waitinglist.added")
        messages.success(self.request, _(
            "We've added you to the waiting list. We will send an email "
            "to {email} as soon as this product gets available again."
        ).format(email=form.instance.email))
        return super().form_valid(form)

    def get_success_url(self):
        return self.get_index_url()


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class WaitingRemoveView(EventViewMixin, TemplateView):
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
