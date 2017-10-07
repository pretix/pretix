import mimetypes
import os

from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import translation
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from django.views.generic import TemplateView, View

from pretix.base.models import (
    CartPosition, InvoiceAddress, ItemVariation, QuestionAnswer, Quota,
    SubEvent, Voucher,
)
from pretix.base.services.cart import (
    CartError, add_items_to_cart, clear_cart, remove_cart_position,
)
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin
from pretix.presale.views.async import AsyncAction
from pretix.presale.views.event import item_group_by_category
from pretix.presale.views.robots import NoSearchIndexViewMixin


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

    @cached_property
    def cart_session(self):
        return cart_session(self.request)

    @cached_property
    def invoice_address(self):
        iapk = self.cart_session.get('invoice_address')
        if not iapk:
            return InvoiceAddress()

        try:
            return InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
        except InvoiceAddress.DoesNotExist:
            return InvoiceAddress()

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
                    'voucher': voucher,
                    'subevent': self.request.POST.get("subevent")
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
                    'voucher': voucher,
                    'subevent': self.request.POST.get("subevent")
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


def create_empty_cart_id(request):
    current_id = request.session.get('current_cart_event_{}'.format(request.event.pk))
    if current_id and current_id in request.session.get('carts', {}):
        del request.session['carts'][current_id]
        del request.session['current_cart_event_{}'.format(request.event.pk)]
    return get_or_create_cart_id(request)


def get_or_create_cart_id(request):
    current_id = request.session.get('current_cart_event_{}'.format(request.event.pk))
    if current_id and current_id in request.session.get('carts', {}):
        return current_id
    else:
        cart_data = {}

        while True:
            new_id = get_random_string(length=32)
            if not CartPosition.objects.filter(cart_id=new_id).exists():
                break

        # Migrate legacy data
        legacy_pos = CartPosition.objects.filter(cart_id=request.session.session_key, event=request.event)
        if legacy_pos.exists():
            legacy_pos.update(cart_id=new_id)
            if 'invoice_address_{}'.format(request.event.pk) in request.session:
                cart_data['invoice_address'] = request.session['invoice_address_{}'.format(request.event.pk)]
            if 'email' in request.session:
                cart_data['email'] = request.session['email']
            if 'contact_form_data' in request.session:
                cart_data['contact_form_data'] = request.session['contact_form_data']
            if 'payment' in request.session:
                cart_data['payment'] = request.session['payment']

        if 'carts' not in request.session:
            request.session['carts'] = {}
        request.session['carts'][new_id] = cart_data
        request.session['current_cart_event_{}'.format(request.event.pk)] = new_id
        return new_id


def cart_session(request):
    request.session.modified = True
    cart_id = get_or_create_cart_id(request)
    return request.session['carts'][cart_id]


class CartRemove(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = remove_cart_position
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        if CartPosition.objects.filter(cart_id=get_or_create_cart_id(self.request)).exists():
            return _('Your cart has been updated.')
        else:
            return _('Your cart is now empty.')

    def post(self, request, *args, **kwargs):
        if 'id' in request.POST:
            return self.do(self.request.event.id, request.POST.get('id'), get_or_create_cart_id(self.request), translation.get_language())
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
        return self.do(self.request.event.id, get_or_create_cart_id(self.request), translation.get_language())


class CartAdd(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = add_items_to_cart
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        return _('The products have been successfully added to your cart.')

    def post(self, request, *args, **kwargs):
        items = self._items_from_post_data()
        if items:
            return self.do(self.request.event.id, items, get_or_create_cart_id(self.request), translation.get_language(),
                           self.invoice_address.pk)
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect(self.get_error_url())


class RedeemView(NoSearchIndexViewMixin, EventViewMixin, TemplateView):
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
            & ~Q(category__is_addon=True)
        )

        vouchq = Q(hide_without_voucher=False)

        if self.voucher.item_id:
            vouchq |= Q(pk=self.voucher.item_id)
            items = items.filter(pk=self.voucher.item_id)
        elif self.voucher.quota_id:
            items = items.filter(quotas__in=[self.voucher.quota_id])

        items = items.filter(vouchq).select_related(
            'category', 'tax_rule',  # for re-grouping
        ).prefetch_related(
            Prefetch('quotas',
                     to_attr='_subevent_quotas',
                     queryset=self.request.event.quotas.filter(subevent=self.subevent)),
            Prefetch('variations', to_attr='available_variations',
                     queryset=ItemVariation.objects.filter(active=True, quotas__isnull=False).prefetch_related(
                         Prefetch('quotas',
                                  to_attr='_subevent_quotas',
                                  queryset=self.request.event.quotas.filter(subevent=self.subevent))
                     ).distinct()),
        ).annotate(
            quotac=Count('quotas'),
            has_variations=Count('variations')
        ).filter(
            quotac__gt=0
        ).distinct().order_by('category__position', 'category_id', 'position', 'name')
        quota_cache = {}

        if self.subevent:
            item_price_override = self.subevent.item_price_overrides
            var_price_override = self.subevent.var_price_overrides
        else:
            item_price_override = {}
            var_price_override = {}

        for item in items:
            if self.voucher.item_id and self.voucher.variation_id:
                item.available_variations = [v for v in item.available_variations if v.pk == self.voucher.variation_id]

            item.order_max = item.max_per_order or int(self.request.event.settings.max_items_per_order)

            if not item.has_variations:
                item._remove = not bool(item._subevent_quotas)
                if self.voucher.allow_ignore_quota or self.voucher.block_quota:
                    item.cached_availability = (Quota.AVAILABILITY_OK, 1)
                else:
                    item.cached_availability = item.check_quotas(subevent=self.subevent, _cache=quota_cache)

                price = item_price_override.get(item.pk, item.default_price)
                price = self.voucher.calculate_price(price)
                item.display_price = item.tax(price)
            else:
                item._remove = False
                for var in item.available_variations:
                    if self.voucher.allow_ignore_quota or self.voucher.block_quota:
                        var.cached_availability = (Quota.AVAILABILITY_OK, 1)
                    else:
                        var.cached_availability = list(var.check_quotas(subevent=self.subevent, _cache=quota_cache))

                    price = var_price_override.get(var.pk, var.price)
                    price = self.voucher.calculate_price(price)
                    var.display_price = item.tax(price)

                item.available_variations = [
                    v for v in item.available_variations if v._subevent_quotas
                ]
                if self.voucher.variation_id:
                    item.available_variations = [v for v in item.available_variations
                                                 if v.pk == self.voucher.variation_id]
                if len(item.available_variations) > 0:
                    item.min_price = min([v.display_price.net if self.request.event.settings.display_net_prices else
                                          v.display_price.gross for v in item.available_variations])
                    item.max_price = max([v.display_price.net if self.request.event.settings.display_net_prices else
                                          v.display_price.gross for v in item.available_variations])

        items = [item for item in items
                 if (len(item.available_variations) > 0 or not item.has_variations) and not item._remove]
        context['options'] = sum([(len(item.available_variations) if item.has_variations else 1)
                                  for item in items])

        # Regroup those by category
        context['items_by_category'] = item_group_by_category(items)

        context['subevent'] = self.subevent

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
                    (Q(expires__gte=now()) | Q(cart_id=get_or_create_cart_id(request)))
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

        self.subevent = None
        if request.event.has_subevents:
            if request.GET.get('subevent'):
                self.subevent = get_object_or_404(SubEvent, event=request.event, pk=request.GET.get('subevent'),
                                                  active=True)

            if self.voucher.subevent:
                self.subevent = self.voucher.subevent
        else:
            pass

        if err:
            messages.error(request, _(err))
            return redirect(eventreverse(request.event, 'presale:event.index'))

        return super().dispatch(request, *args, **kwargs)


class AnswerDownload(EventViewMixin, View):
    def get(self, request, *args, **kwargs):
        answid = kwargs.get('answer')
        answer = get_object_or_404(
            QuestionAnswer,
            cartposition__cart_id=get_or_create_cart_id(self.request),
            id=answid
        )
        if not answer.file:
            return Http404()

        ftype, _ = mimetypes.guess_type(answer.file.name)
        resp = FileResponse(answer.file, content_type=ftype or 'application/binary')
        resp['Content-Disposition'] = 'attachment; filename="{}-cart-{}"'.format(
            self.request.event.slug.upper(),
            os.path.basename(answer.file.name).split('.', 1)[1]
        )
        return resp
