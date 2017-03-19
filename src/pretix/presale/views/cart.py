from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import translation
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from django.views.generic import TemplateView, View

from pretix.base.decimal import round_decimal
from pretix.base.models import CartPosition, Quota, Voucher
from pretix.base.services.cart import (
    CartError, add_items_to_cart, clear_cart, remove_cart_position,
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

    def _item_from_post_value(self, key, value, voucher=None):
        if value.strip() == '' or '_' not in key:
            return

        if not key.startswith('item_') and not key.startswith('variation_'):
            return

        parts = key.split("_")
        try:
            amount = int(value)
        except ValueError:
            raise CartError(_('Please enter numbers only.'))
        if amount < 0:
            raise CartError(_('Please enter positive numbers only.'))
        elif amount == 0:
            return

        price = self.request.POST.get('price_' + "_".join(parts[1:]), "")
        if key.startswith('item_'):
            try:
                return {
                    'item': int(parts[1]),
                    'variation': None,
                    'count': amount,
                    'price': price,
                    'voucher': voucher
                }
            except ValueError:
                raise CartError(_('Please enter numbers only.'))
        elif key.startswith('variation_'):
            try:
                return {
                    'item': int(parts[1]),
                    'variation': int(parts[2]),
                    'count': amount,
                    'price': price,
                    'voucher': voucher
                }
            except ValueError:
                raise CartError(_('Please enter numbers only.'))

    def _items_from_post_data(self):
        """
        Parses the POST data and returns a list of tuples in the
        form (item id, variation id or None, number)
        """

        # Compatibility patch that makes the frontend code a lot easier
        req_items = list(self.request.POST.lists())
        if '_voucher_item' in self.request.POST and '_voucher_code' in self.request.POST:
            req_items.append((
                '%s' % self.request.POST['_voucher_item'], ('1',)
            ))
            pass

        items = []
        for key, values in req_items:
            for value in values:
                try:
                    item = self._item_from_post_value(key, value, self.request.POST.get('_voucher_code'))
                except CartError as e:
                    messages.error(self.request, str(e))
                    return
                if item:
                    items.append(item)

        if len(items) == 0:
            messages.warning(self.request, _('You did not select any products.'))
            return []
        return items


class CartRemove(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = remove_cart_position
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        if CartPosition.objects.filter(cart_id=self.request.session.session_key).exists():
            return _('Your cart has been updated.')
        else:
            return _('Your cart is now empty.')

    def post(self, request, *args, **kwargs):
        if 'id' in request.POST:
            return self.do(self.request.event.id, request.POST.get('id'), self.request.session.session_key, translation.get_language())
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect(self.get_error_url())


class CartClear(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = clear_cart
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        return _('Your cart is now empty.')

    def post(self, request, *args, **kwargs):
        return self.do(self.request.event.id, self.request.session.session_key, translation.get_language())


class CartAdd(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = add_items_to_cart
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        return _('The products have been successfully added to your cart.')

    def post(self, request, *args, **kwargs):
        items = self._items_from_post_data()
        if items:
            return self.do(self.request.event.id, items, self.request.session.session_key, translation.get_language())
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
        context['max_times'] = self.voucher.max_usages - self.voucher.redeemed

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

            item.order_max = item.max_per_order or int(self.request.event.settings.max_items_per_order)

            item.has_variations = item.variations.exists()
            if not item.has_variations:
                if self.voucher.allow_ignore_quota or self.voucher.block_quota:
                    item.cached_availability = (Quota.AVAILABILITY_OK, 1)
                else:
                    item.cached_availability = item.check_quotas()
                item.price = self.voucher.calculate_price(item.default_price)
                if self.request.event.settings.display_net_prices:
                    item.price -= round_decimal(item.price * (1 - 100 / (100 + item.tax_rate)))
            else:
                for var in item.available_variations:
                    if self.voucher.allow_ignore_quota or self.voucher.block_quota:
                        var.cached_availability = (Quota.AVAILABILITY_OK, 1)
                    else:
                        var.cached_availability = list(var.check_quotas())
                    var.display_price = self.voucher.calculate_price(var.price)
                    if self.request.event.settings.display_net_prices:
                        var.display_price -= round_decimal(var.display_price * (1 - 100 / (100 + item.tax_rate)))

                if len(item.available_variations) > 0:
                    item.min_price = min([v.display_price for v in item.available_variations])
                    item.max_price = max([v.display_price for v in item.available_variations])

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
            v = v.strip()
            try:
                self.voucher = Voucher.objects.get(code=v, event=request.event)
                if self.voucher.redeemed >= self.voucher.max_usages:
                    err = error_messages['voucher_redeemed']
                if self.voucher.valid_until is not None and self.voucher.valid_until < now():
                    err = error_messages['voucher_expired']

                redeemed_in_carts = CartPosition.objects.filter(
                    Q(voucher=self.voucher) & Q(event=request.event) &
                    (Q(expires__gte=now()) | Q(cart_id=request.session.session_key))
                )
                v_avail = self.voucher.max_usages - self.voucher.redeemed - redeemed_in_carts.count()
                if v_avail < 1:
                    err = error_messages['voucher_redeemed']
            except Voucher.DoesNotExist:
                err = error_messages['voucher_invalid']
        else:
            return redirect(eventreverse(request.event, 'presale:event.index'))

        if request.event.presale_start and now() < request.event.presale_start:
            err = error_messages['not_started']
        if request.event.presale_end and now() > request.event.presale_end:
            err = error_messages['ended']

        if err:
            messages.error(request, _(err))
            return redirect(eventreverse(request.event, 'presale:event.index'))

        return super().dispatch(request, *args, **kwargs)
