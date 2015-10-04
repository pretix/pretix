from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View

from pretix.base.services.cart import (
    CartError, add_items_to_cart, remove_items_from_cart,
)
from pretix.presale.views import EventViewMixin


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


class CartRemove(EventViewMixin, CartActionMixin, View):

    def post(self, *args, **kwargs):
        items = self._items_from_post_data()
        if not items:
            return redirect(self.get_failure_url())

        remove_items_from_cart(self.request.event.identity, items, self.request.session.session_key)
        messages.success(self.request, _('Your cart has been updated.'))
        return redirect(self.get_success_url())


class CartAdd(EventViewMixin, CartActionMixin, View):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        items = self._items_from_post_data()
        return self.process(items)

    def process(self, items):
        try:
            add_items_to_cart(self.request.event.identity, items, self.request.session.session_key)
            messages.success(self.request, _('The products have been successfully added to your cart.'))
            return redirect(self.get_success_url())
        except CartError as e:
            messages.error(self.request, str(e))
            return redirect(self.get_failure_url())
