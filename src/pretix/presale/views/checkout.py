from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View

from pretix.base.models import CartPosition
from pretix.base.services.cart import CartError
from pretix.base.signals import validate_cart
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.checkoutflow import get_checkout_flow
from pretix.presale.views.cart import get_or_create_cart_id


class CheckoutView(View):
    def dispatch(self, request, *args, **kwargs):

        self.request = request
        cart_pos = CartPosition.objects.filter(
            cart_id=get_or_create_cart_id(request), event=self.request.event
        )

        if not cart_pos.exists() and "async_id" not in request.GET:
            messages.error(request, _("Your cart is empty"))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        if not request.event.presale_is_running:
            messages.error(request, _("The presale for this event is over or has not yet started."))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        cart_error = None
        try:
            validate_cart.send(sender=self.request.event, positions=cart_pos)
        except CartError as e:
            cart_error = e

        flow = get_checkout_flow(self.request.event)
        previous_step = None
        for step in flow:
            if not step.is_applicable(request):
                continue
            if step.requires_valid_cart and cart_error:
                messages.error(request, str(cart_error))
                return redirect(previous_step.get_step_url() if previous_step
                                else eventreverse(self.request.event, 'presale:event.index'))

            if 'step' not in kwargs:
                return redirect(step.get_step_url())
            is_selected = (step.identifier == kwargs.get('step', ''))
            if "async_id" not in request.GET and not is_selected and not step.is_completed(request, warn=not is_selected):
                return redirect(step.get_step_url())
            if is_selected:
                if request.method.lower() in self.http_method_names:
                    handler = getattr(step, request.method.lower(), self.http_method_not_allowed)
                else:
                    handler = self.http_method_not_allowed
                return handler(request)
            else:
                previous_step = step
        raise Http404()
