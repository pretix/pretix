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


class CheckoutView(View):
    def dispatch(self, request, *args, **kwargs):
        self.request = request
        cart_pos = CartPosition.objects.filter(
            cart_id=self.request.session.session_key, event=self.request.event
        )

        if not cart_pos.exists() and "async_id" not in request.GET:
            messages.error(request, _("Your cart is empty"))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        try:
            validate_cart.send(sender=self.request.event, positions=cart_pos)
        except CartError as e:
            messages.error(request, str(e))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        flow = get_checkout_flow(self.request.event)
        for step in flow:
            if not step.is_applicable(request):
                continue
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
        raise Http404()
