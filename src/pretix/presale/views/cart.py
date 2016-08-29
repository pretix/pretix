from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from django.views.generic import TemplateView, View

from pretix.base.models import Quota, Voucher
from pretix.base.services.cart import (
    CartError, add_items_to_cart, remove_items_from_cart,
)
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin
from pretix.presale.views.async import AsyncAction
from pretix.presale.views.event import item_group_by_category


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

        # Compatibility patch that makes the frontend code a lot easier
        req_items = list(self.request.POST.items())
        if '_voucher_item' in self.request.POST and '_voucher_code' in self.request.POST:
            req_items.append((
                '%s_voucher' % self.request.POST['_voucher_item'], self.request.POST['_voucher_code']
            ))
            pass

        items = []
        for key, value in req_items:
            if value.strip() == '' or '_' not in key:
                continue

            parts = key.split("_")
            if parts[-1] == "voucher":
                voucher = value
                value = 1
                parts = parts[:-1]
            else:
                voucher = None

            try:
                amount = int(value)
            except ValueError:
                messages.error(self.request, _('Please enter numbers only.'))
                return []
            if amount <= 0:
                messages.error(self.request, _('Please enter positive numbers only.'))
                return []

            price = self.request.POST.get('price_' + "_".join(parts[1:]), "")
            if key.startswith('item_'):
                try:
                    items.append({
                        'item': int(parts[1]),
                        'variation': None,
                        'count': amount,
                        'price': price,
                        'voucher': voucher
                    })
                except ValueError:
                    messages.error(self.request, _('Please enter numbers only.'))
                    return []
            elif key.startswith('variation_'):
                try:
                    items.append({
                        'item': int(parts[1]),
                        'variation': int(parts[2]),
                        'count': amount,
                        'price': price,
                        'voucher': voucher
                    })
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


class RedeemView(EventViewMixin, TemplateView):
    template_name = "pretixpresale/event/voucher.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['voucher'] = self.voucher

        # Fetch all items
        items = self.request.event.items.all().filter(
            Q(active=True)
            & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
            & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
        )

        vouchq = Q(hide_without_voucher=False)

        if self.voucher.item_id:
            vouchq |= Q(pk=self.voucher.item_id)
            items = items.filter(pk=self.voucher.item_id)
        elif self.voucher.quota_id:
            items = items.filter(quotas__in=[self.voucher.quota_id])

        items = items.filter(vouchq).select_related(
            'category',  # for re-grouping
        ).prefetch_related(
            'quotas', 'variations__quotas', 'quotas__event'  # for .availability()
        ).annotate(quotac=Count('quotas')).filter(
            quotac__gt=0
        ).distinct().order_by('category__position', 'category_id', 'position', 'name')

        for item in items:
            item.available_variations = list(item.variations.filter(active=True, quotas__isnull=False).distinct())
            if self.voucher.item_id and self.voucher.variation_id:
                item.available_variations = [v for v in item.available_variations if v.pk == self.voucher.variation_id]

            item.has_variations = item.variations.exists()
            if not item.has_variations:
                if self.voucher.allow_ignore_quota or self.voucher.block_quota:
                    item.cached_availability = (Quota.AVAILABILITY_OK, 1)
                else:
                    item.cached_availability = item.check_quotas()
                if self.voucher.price is not None:
                    item.price = self.voucher.price
                else:
                    item.price = item.default_price
            else:
                for var in item.available_variations:
                    if self.voucher.allow_ignore_quota or self.voucher.block_quota:
                        var.cached_availability = (Quota.AVAILABILITY_OK, 1)
                    else:
                        var.cached_availability = list(var.check_quotas())
                    if self.voucher.price is not None:
                        var.price = self.voucher.price
                    else:
                        var.price = var.default_price if var.default_price is not None else item.default_price

                if len(item.available_variations) > 0:
                    item.min_price = min([v.price for v in item.available_variations])
                    item.max_price = max([v.price for v in item.available_variations])

        items = [item for item in items if len(item.available_variations) > 0 or not item.has_variations]
        context['options'] = sum([(len(item.available_variations) if item.has_variations else 1)
                                  for item in items])

        # Regroup those by category
        context['items_by_category'] = item_group_by_category(items)

        return context

    def dispatch(self, request, *args, **kwargs):
        from pretix.base.services.cart import error_messages

        err = None
        v = request.GET.get('voucher')

        if v:
            try:
                self.voucher = Voucher.objects.get(code=v, event=request.event)
                if self.voucher.redeemed:
                    err = error_messages['voucher_redeemed']
                if self.voucher.valid_until is not None and self.voucher.valid_until < now():
                    err = error_messages['voucher_expired']
            except Voucher.DoesNotExist:
                err = error_messages['voucher_invalid']
        else:
            return redirect(eventreverse(request.event, 'presale:event.index'))

        if request.event.presale_start and now() < request.event.presale_start:
            err = error_messages['not_started']
        if request.event.presale_end and now() > request.event.presale_end:
            err = error_messages['ended']

        if err:
            messages.error(request, err)
            return redirect(eventreverse(request.event, 'presale:event.index'))

        return super().dispatch(request, *args, **kwargs)
