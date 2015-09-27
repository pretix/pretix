import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.shortcuts import redirect
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View

from pretix.base.models import (
    CartPosition, EventLock, Item, ItemVariation, Quota,
)
from pretix.base.services.cart import (
    CartError, add_items_to_cart, remove_items_from_cart,
)
from pretix.presale.views import (
    EventViewMixin, LoginOrGuestRequiredMixin, user_cart_q,
)


class CartActionMixin:

    def get_next_url(self):
        if "next" in self.request.GET and '://' not in self.request.GET:
            return self.request.GET.get('next')
        elif "HTTP_REFERER" in self.request.META:
            return self.request.META.get('HTTP_REFERER')
        else:
            return reverse('presale:event.index', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug,
            })

    def get_success_url(self):
        return self.get_next_url()

    def get_failure_url(self):
        return self.get_next_url()

    def _items_from_post_data(self):
        """
        Parses the POST data and returns a list of tuples in the
        form (item id, variation id or None, number)
        """
        items = []
        for key, value in self.request.POST.items():
            if value.strip() == '':
                continue
            if key.startswith('item_'):
                try:
                    items.append((key.split("_")[1], None, int(value)))
                except ValueError:
                    messages.error(self.request, _('Please enter numbers only.'))
                    return []
            elif key.startswith('variation_'):
                try:
                    items.append((key.split("_")[1], key.split("_")[2], int(value)))
                except ValueError:
                    messages.error(self.request, _('Please enter numbers only.'))
                    return []
        if len(items) == 0:
            messages.warning(self.request, _('You did not select any products.'))
            return []
        return items


class CartRemove(EventViewMixin, CartActionMixin, LoginOrGuestRequiredMixin, View):

    def post(self, *args, **kwargs):
        items = self._items_from_post_data()
        if not items:
            return redirect(self.get_failure_url())

        remove_items_from_cart(self.request.event.identity, items, self.request.user.od,
                               self.request.session.session_key)
        messages.success(self.request, _('Your cart has been updated.'))
        return redirect(self.get_success_url())


class CartAdd(EventViewMixin, CartActionMixin, View):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        items = self._items_from_post_data()

        # We do not use LoginRequiredMixin here, as we want to store stuff into the
        # session before redirecting to login
        if not request.user.is_authenticated() and 'guest_email' not in request.session:
            request.session['cart_tmp'] = json.dumps(items)
            return redirect_to_login(
                self.get_success_url(), reverse('presale:event.checkout.login', kwargs={
                    'organizer': request.event.organizer.slug,
                    'event': request.event.slug,
                }), 'next'
            )

        return self.process(items)

    def process(self, items):
        try:
            add_items_to_cart(self.request.event.identity, items, self.request.user.id,
                              self.request.session.session_key)
            messages.success(self.request, _('The products have been successfully added to your cart.'))
            return redirect(self.get_success_url())
        except CartError as e:
            messages.error(self.request, str(e))
            return redirect(self.get_failure_url())
