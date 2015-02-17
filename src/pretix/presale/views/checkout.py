from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.views.generic import View
from django.utils.translation import ugettext_lazy as _

from pretix.presale.views import EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin


class CheckoutStart(EventViewMixin, CartDisplayMixin, EventLoginRequiredMixin, View):

    def get_failure_url(self):
        return reverse('presale:event.index', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        })

    def get(self, *args, **kwargs):
        cart = self.get_cart()
        if not cart['positions']:
            messages.error(self.request,
                           _("Your cart is empty") % self.event.max_items_per_order)
            return redirect(self.get_failure_url())
