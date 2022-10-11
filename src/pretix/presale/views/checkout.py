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
from urllib.parse import quote

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from pretix.base.services.cart import CartError
from pretix.base.signals import validate_cart
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.checkoutflow import get_checkout_flow
from pretix.presale.views import (
    allow_frame_if_namespaced, cart_exists, get_cart,
    iframe_entry_view_wrapper,
)


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class CheckoutView(View):

    def get_index_url(self, request):
        kwargs = {}
        if 'cart_namespace' in self.kwargs:
            kwargs['cart_namespace'] = self.kwargs['cart_namespace']
        return eventreverse(self.request.event, 'presale:event.index', kwargs=kwargs) + '?require_cookie=true'

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        if not cart_exists(request) and "async_id" not in request.GET:
            messages.error(request, _("Your cart is empty"))
            return self.redirect(self.get_index_url(self.request))

        if not request.event.presale_is_running:
            messages.error(request, _("The booking period for this event is over or has not yet started."))
            return self.redirect(self.get_index_url(self.request))

        cart_error = None
        try:
            validate_cart.send(sender=self.request.event, positions=get_cart(request))
        except CartError as e:
            cart_error = e

        flow = request._checkout_flow = get_checkout_flow(self.request.event)
        previous_step = None
        for step in flow:
            if not step.is_applicable(request):
                continue
            if step.requires_valid_cart and cart_error:
                messages.error(request, str(cart_error))
                return self.redirect(previous_step.get_step_url(request) if previous_step else self.get_index_url(request))

            if 'step' not in kwargs:
                return self.redirect(step.get_step_url(request))
            is_selected = (step.identifier == kwargs.get('step', ''))
            if "async_id" not in request.GET and not is_selected and not step.is_completed(request, warn=not is_selected):
                return self.redirect(step.get_step_url(request))
            if is_selected:
                if request.method.lower() in self.http_method_names:
                    handler = getattr(step, request.method.lower(), self.http_method_not_allowed)
                else:
                    handler = self.http_method_not_allowed
                return handler(request)
            else:
                previous_step = step
                step.c_is_before = True
                step.c_resolved_url = step.get_step_url(request)
        raise Http404()

    def redirect(self, url):
        if 'cart_id' in self.request.GET:
            url += ('&' if '?' in url else '?') + 'cart_id=' + quote(self.request.GET.get('cart_id'))
        return redirect(url)
