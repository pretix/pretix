from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import ugettext as _
from django.views.generic import View

from pretix.base.services.cart import (
    CartError, add_items_to_cart, remove_items_from_cart,
)
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin
from pretix.presale.views.async import AsyncAction


class CartActionMixin:

    def get_next_url(self):
        if "next" in self.request.GET and '://' not in self.request.GET.get('next'):
            return self.request.GET.get('next')
        else:
            return eventreverse(self.request.event, 'presale:event.index')

    def get_success_url(self, value=None):
        return self.get_next_url()

    def get_error_url(self):
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
                    items.append((int(key.split("_")[1]), None, int(value)))
                except ValueError:
                    messages.error(self.request, _('Please enter numbers only.'))
                    return []
            elif key.startswith('variation_'):
                try:
                    items.append((int(key.split("_")[1]), int(key.split("_")[2]), int(value)))
                except ValueError:
                    messages.error(self.request, _('Please enter numbers only.'))
                    return []
        if len(items) == 0:
            messages.warning(self.request, _('You did not select any products.'))
            return []
        return items


class CartRemove(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = remove_items_from_cart

    def get_success_message(self, value):
        return _('Your cart has been updated.')

    def get_error_message(self, exception):
        if isinstance(exception, dict) and exception['exc_type'] == 'CartError':
            return exception['exc_message']
        elif isinstance(exception, CartError):
            return str(exception)
        return super().get_error_message(exception)

    def post(self, request, *args, **kwargs):
        items = self._items_from_post_data()
        if items:
            return self.do(self.request.event.id, items, self.request.session.session_key)
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect(self.get_error_url())


class CartAdd(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = add_items_to_cart

    def get_success_message(self, value):
        return _('The products have been successfully added to your cart.')

    def get_error_message(self, exception):
        if isinstance(exception, dict) and exception['exc_type'] == 'CartError':
            return exception['exc_message']
        elif isinstance(exception, CartError):
            return str(exception)
        return super().get_error_message(exception)

    def post(self, request, *args, **kwargs):
        items = self._items_from_post_data()
        if items:
            return self.do(self.request.event.id, items, self.request.session.session_key)
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect(self.get_error_url())
