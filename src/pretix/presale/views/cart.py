import json
import mimetypes
import os
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.cache import caches
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import translation
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.http import is_safe_url
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView, View
from django_scopes import scopes_disabled

from pretix.base.models import (
    CartPosition, InvoiceAddress, QuestionAnswer, SubEvent, Voucher,
)
from pretix.base.services.cart import (
    CartError, add_items_to_cart, apply_voucher, clear_cart, error_messages,
    remove_cart_position,
)
from pretix.base.views.tasks import AsyncAction
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import (
    EventViewMixin, allow_cors_if_namespaced, allow_frame_if_namespaced,
    iframe_entry_view_wrapper,
)
from pretix.presale.views.event import (
    get_grouped_items, item_group_by_category,
)
from pretix.presale.views.robots import NoSearchIndexViewMixin

try:
    widget_data_cache = caches['redis']
except:
    widget_data_cache = caches['default']


class CartActionMixin:

    def get_next_url(self):
        if "next" in self.request.GET and is_safe_url(self.request.GET.get("next"), allowed_hosts=None):
            u = self.request.GET.get('next')
        else:
            kwargs = {}
            if 'cart_namespace' in self.kwargs:
                kwargs['cart_namespace'] = self.kwargs['cart_namespace']
            u = eventreverse(self.request.event, 'presale:event.index', kwargs=kwargs)
        if '?' in u:
            u += '&require_cookie=true'
        else:
            u += '?require_cookie=true'
        disclose_cart_id = (
            'iframe' in self.request.GET or settings.SESSION_COOKIE_NAME not in self.request.COOKIES
        ) and self.kwargs.get('cart_namespace')
        if disclose_cart_id:
            cart_id = get_or_create_cart_id(self.request)
            u += '&cart_id={}'.format(cart_id)
        return u

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
            with scopes_disabled():
                return InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
        except InvoiceAddress.DoesNotExist:
            return InvoiceAddress()

    def _item_from_post_value(self, key, value, voucher=None):
        if value.strip() == '' or '_' not in key:
            return

        if not key.startswith('item_') and not key.startswith('variation_') and not key.startswith('seat_'):
            return

        parts = key.split("_")
        price = self.request.POST.get('price_' + "_".join(parts[1:]), "")

        if key.startswith('seat_'):
            try:
                return {
                    'item': int(parts[1]),
                    'variation': int(parts[2]) if len(parts) > 2 else None,
                    'count': 1,
                    'seat': value,
                    'price': price,
                    'voucher': voucher,
                    'subevent': self.request.POST.get("subevent")
                }
            except ValueError:
                raise CartError(_('Please enter numbers only.'))

        try:
            amount = int(value)
        except ValueError:
            raise CartError(_('Please enter numbers only.'))
        if amount < 0:
            raise CartError(_('Please enter positive numbers only.'))
        elif amount == 0:
            return

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
        Parses the POST data and returns a list of dictionaries
        """

        # Compatibility patch that makes the frontend code a lot easier
        req_items = list(self.request.POST.lists())
        if '_voucher_item' in self.request.POST and '_voucher_code' in self.request.POST:
            req_items.append((
                '%s' % self.request.POST['_voucher_item'], ('1',)
            ))
            pass

        items = []
        if 'raw' in self.request.POST:
            items += json.loads(self.request.POST.get("raw"))
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


@scopes_disabled()
def generate_cart_id(request=None, prefix=''):
    """
    Generates a random new cart ID that is not currently in use, with an optional pretix.
    """
    while True:
        new_id = prefix + get_random_string(length=48 - len(prefix))
        if request:
            if not request.session.session_key:
                request.session.create()
            new_id += "@" + request.session.session_key
        if not CartPosition.objects.filter(cart_id=new_id).exists():
            return new_id


def create_empty_cart_id(request, replace_current=True):
    """
    Forcefully creates a new empty cart for the current session. Behaves like get_or_create_cart_id,
    except that it ignores the current state of the session. If replace_current is active, the
    current cart session for this event is deleted as well.

    This is currently only invoked after an order has been created to make sure that all forms during
    checkout will show empty again if the same browser starts buying tickets again.
    """
    session_keyname = 'current_cart_event_{}'.format(request.event.pk)
    prefix = ''
    if request.resolver_match and request.resolver_match.kwargs.get('cart_namespace'):
        session_keyname += '_' + request.resolver_match.kwargs.get('cart_namespace')
        prefix = request.resolver_match.kwargs.get('cart_namespace')

    if 'carts' not in request.session:
        request.session['carts'] = {}

    new_id = generate_cart_id(request, prefix=prefix)
    request.session['carts'][new_id] = {}

    if replace_current:
        current_id = request.session.get(session_keyname)
        if current_id and current_id in request.session.get('carts', {}):
            del request.session['carts'][current_id]
            del request.session[session_keyname]
        request.session[session_keyname] = new_id
    return new_id


def get_or_create_cart_id(request, create=True):
    """
    This method returns the cart ID in use for this request or creates a new cart ID if required.

    Before pretix 1.8.0, the user's session cookie was used as the cart ID in the database.
    With the cart session data isolation introduced in 1.8.0 (see cart_session()) this changed
    drastically. Now, a different random cart ID is used for every event and stored to the
    user's session with the 'current_cart_event_42' key (with 42 being the event ID).

    This became even more relevant and complex with the introduction of the pretix widget in 1.9.0.
    Since the widget operates from a different origin, it requires us to lower some security walls
    in order to function correctly:

    * The checkout and order views can no longer send X-Frame-Options: DENY headers as we include
      those pages in an iframe. This makes our users vulnerable to clickjacking. Possible scenario: A
      third-party website could trick you into submitting an order that you currently have in your cart.

    * The cart add view needs to drop CSRF protection and set Access-Control-Allow-Origin: *. This makes
      our users vulnerable to CSRF attacks adding unwanted products to their carts. Cross-Origin is not
      that much of an issue since we can't set Access-Control-Allow-Credentials for origin * either way,
      but on the other hand this also prevents us to change the current cart for legitimate reasons.

    We can mitigate all of these issues at the same time with the very simple strategy on only lowering
    these walls at unguessable URLs. This makes it impossible for an attacker to create an exploit with
    real-world impact.

    Therefore, we introduce cart namespacing in pretix 1.9.0. In addition to your default session that you
    have at /orga/event/ as usual, you will have a different cart session with a different cart ID at
    /orga/event/w/mysecretnonce123/. Such a namespace parameter can be passed to all views relevant to the
    widget (e.g. /orga/event/w/mysecretnonce123/cart/add) that are not already unguessable
    (like /orga/event/orders/ABCDE/secret123465456/).

    The actual cart IDs for those namespaced carts will then be stored at
    request.session['current_cart_event_42_mysecretnonce123'].

    However, we still need to work around the issue that we can't use Access-Control-Allow-Credentials
    but want to invoke /cart/add via a cross-origin request. This leads to /cart/add creating a new
    cart session every time it is invoked cross-origin by default. We solve this by returning the newly
    created cart ID from /cart/add in the response and allow passing it as the take_cart_id query parameter
    to the view in the iframe or to subsequent /cart/add requests.

    As an additional precaution, take_cart_id will only be honoured on POST requests or if there is an
    actual cart with this ID. This reduces the likelihood of strange behaviour if someone accidentally
    shares a link that includes this parameter.

    This method migrates legacy sessions created before the upgrade to 1.8.0 on a best-effort basis,
    meaning that the migration does not respect plugin-specific data and works best if the user only
    used the session for one event at the time of migration.

    If ``create`` is ``False`` and no session currently exists, ``None`` will be returned.
    """
    session_keyname = 'current_cart_event_{}'.format(request.event.pk)
    prefix = ''
    if request.resolver_match and request.resolver_match.kwargs.get('cart_namespace'):
        session_keyname += '_' + request.resolver_match.kwargs.get('cart_namespace')
        prefix = request.resolver_match.kwargs.get('cart_namespace')

    current_id = orig_current_id = request.session.get(session_keyname)
    if prefix and 'take_cart_id' in request.GET:
        pos = CartPosition.objects.filter(event=request.event, cart_id=request.GET.get('take_cart_id'))
        if request.method == "POST" or pos.exists():
            current_id = request.GET.get('take_cart_id')

    if current_id and current_id in request.session.get('carts', {}):
        if current_id != orig_current_id:
            request.session[session_keyname] = current_id
        return current_id
    else:
        cart_data = {}
        if prefix and 'take_cart_id' in request.GET and current_id:
            new_id = current_id
            cached_widget_data = widget_data_cache.get('widget_data_{}'.format(current_id))
            if cached_widget_data:
                cart_data['widget_data'] = cached_widget_data
        else:
            if not create:
                return None
            new_id = generate_cart_id(request, prefix=prefix)

        if 'widget_data' not in cart_data and 'widget_data' in request.GET:
            try:
                cart_data['widget_data'] = json.loads(request.GET.get('widget_data'))
            except ValueError:
                pass

        if 'carts' not in request.session:
            request.session['carts'] = {}
        if new_id not in request.session['carts']:
            request.session['carts'][new_id] = cart_data
        request.session[session_keyname] = new_id
        return new_id


def cart_session(request):
    """
    Before pretix 1.8.0, all checkout-related information (like the entered email address) was stored
    in the user's regular session dictionary. This led to data interference and leaks for example if a
    user simultaneously buys tickets for two events.

    Starting with 1.8.0, this information is stored in separate dictionaries in the user's session within
    the new request.session['carts'] dictionary. This method provides convenient access to the currently
    active cart session sub-dictionary for read and write access.
    """
    request.session.modified = True
    cart_id = get_or_create_cart_id(request)
    return request.session['carts'][cart_id]


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class CartApplyVoucher(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = apply_voucher
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        return _('We applied the voucher to as many products in your cart as we could.')

    def post(self, request, *args, **kwargs):
        if 'voucher' in request.POST:
            return self.do(self.request.event.id, request.POST.get('voucher'), get_or_create_cart_id(self.request),
                           translation.get_language(), request.sales_channel.identifier)
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect(self.get_error_url())


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class CartRemove(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = remove_cart_position
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        if CartPosition.objects.filter(cart_id=get_or_create_cart_id(self.request)).exists():
            return _('Your cart has been updated.')
        else:
            create_empty_cart_id(self.request)
            return _('Your cart is now empty.')

    def post(self, request, *args, **kwargs):
        if 'id' in request.POST:
            return self.do(self.request.event.id, request.POST.get('id'), get_or_create_cart_id(self.request),
                           translation.get_language(), request.sales_channel.identifier)
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url()
                })
            else:
                return redirect(self.get_error_url())


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class CartClear(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = clear_cart
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        create_empty_cart_id(self.request)
        return _('Your cart is now empty.')

    def post(self, request, *args, **kwargs):
        return self.do(self.request.event.id, get_or_create_cart_id(self.request), translation.get_language(),
                       request.sales_channel.identifier)


@method_decorator(allow_cors_if_namespaced, 'dispatch')
@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class CartAdd(EventViewMixin, CartActionMixin, AsyncAction, View):
    task = add_items_to_cart
    known_errortypes = ['CartError']

    def get_success_message(self, value):
        return _('The products have been successfully added to your cart.')

    def _ajax_response_data(self):
        cart_id = get_or_create_cart_id(self.request)
        return {
            'cart_id': cart_id,
            'has_cart': CartPosition.objects.filter(cart_id=cart_id, event=self.request.event).exists()
        }

    def post(self, request, *args, **kwargs):
        cart_id = get_or_create_cart_id(self.request)
        if "widget_data" in request.POST:
            try:
                widget_data = json.loads(request.POST.get("widget_data", "{}"))
                if not isinstance(widget_data, dict):
                    widget_data = {}
            except ValueError:
                widget_data = {}
            else:
                widget_data_cache.set('widget_data_{}'.format(cart_id), widget_data, 600)
                cs = cart_session(request)
                cs['widget_data'] = widget_data
        else:
            cs = cart_session(request)
            widget_data = cs.get('widget_data', {})

        items = self._items_from_post_data()
        if items:
            return self.do(self.request.event.id, items, cart_id, translation.get_language(),
                           self.invoice_address.pk, widget_data, self.request.sales_channel.identifier)
        else:
            if 'ajax' in self.request.GET or 'ajax' in self.request.POST:
                return JsonResponse({
                    'redirect': self.get_error_url(),
                    'success': False,
                    'message': _(error_messages['empty'])
                })
            else:
                return redirect(self.get_error_url())


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class RedeemView(NoSearchIndexViewMixin, EventViewMixin, TemplateView):
    template_name = "pretixpresale/event/voucher.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['voucher'] = self.voucher
        context['max_times'] = self.voucher.max_usages - self.voucher.redeemed

        # Fetch all items
        items, display_add_to_cart = get_grouped_items(self.request.event, self.subevent,
                                                       voucher=self.voucher, channel=self.request.sales_channel.identifier)

        # Calculate how many options the user still has. If there is only one option, we can
        # check the box right away ;)
        context['options'] = sum([(len(item.available_variations) if item.has_variations else 1)
                                  for item in items])

        context['allfree'] = all(
            item.display_price.gross == Decimal('0.00') for item in items if not item.has_variations
        ) and all(
            all(
                var.display_price.gross == Decimal('0.00')
                for var in item.available_variations
            )
            for item in items if item.has_variations
        )

        # Regroup those by category
        context['items_by_category'] = item_group_by_category(items)

        context['subevent'] = self.subevent
        context['seating_available'] = self.request.event.settings.seating_choice and self.voucher.seating_available(self.subevent)

        context['new_tab'] = (
            'require_cookie' in self.request.GET and
            settings.SESSION_COOKIE_NAME not in self.request.COOKIES
            # Cookies are not supported! Lets just make the form open in a new tab
        )

        if self.request.event.settings.redirect_to_checkout_directly:
            context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.checkout.start',
                                                    kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
        else:
            context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.index',
                                                    kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
        if context['cart_redirect'].startswith('https:'):
            context['cart_redirect'] = '/' + context['cart_redirect'].split('/', 3)[3]

        return context

    def dispatch(self, request, *args, **kwargs):
        from pretix.base.services.cart import error_messages

        err = None
        v = request.GET.get('voucher')

        if v:
            v = v.strip()
            try:
                self.voucher = Voucher.objects.get(code__iexact=v, event=request.event)
                if self.voucher.redeemed >= self.voucher.max_usages:
                    err = error_messages['voucher_redeemed']
                if self.voucher.valid_until is not None and self.voucher.valid_until < now():
                    err = error_messages['voucher_expired']
                if self.voucher.item is not None and self.voucher.item.is_available() is False:
                    err = error_messages['voucher_item_not_available']

                redeemed_in_carts = CartPosition.objects.filter(
                    Q(voucher=self.voucher) & Q(event=request.event) &
                    (Q(expires__gte=now()) | Q(cart_id=get_or_create_cart_id(request)))
                )
                v_avail = self.voucher.max_usages - self.voucher.redeemed - redeemed_in_carts.count()
                if v_avail < 1 and not err:
                    err = error_messages['voucher_redeemed_cart'] % self.request.event.settings.reservation_time
            except Voucher.DoesNotExist:
                if self.request.event.organizer.accepted_gift_cards.filter(secret__iexact=request.GET.get("voucher")).exists():
                    err = error_messages['gift_card']
                else:
                    err = error_messages['voucher_invalid']
        else:
            return redirect(self.get_index_url())

        if request.event.presale_start and now() < request.event.presale_start:
            err = error_messages['not_started']
        if request.event.presale_end and now() > request.event.presale_end:
            err = error_messages['ended']

        self.subevent = None
        if request.event.has_subevents:
            if request.GET.get('subevent'):
                self.subevent = get_object_or_404(SubEvent, event=request.event, pk=request.GET.get('subevent'),
                                                  active=True)

            if hasattr(self, 'voucher') and self.voucher.subevent:
                self.subevent = self.voucher.subevent
        else:
            pass

        if err:
            messages.error(request, _(err))
            return redirect(self.get_index_url())

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if 'iframe' in request.GET and 'require_cookie' not in request.GET:
            return redirect(request.get_full_path() + '&require_cookie=1')

        if len(self.request.GET.get('widget_data', '{}')) > 3:
            # We've been passed data from a widget, we need to create a cart session to store it.
            get_or_create_cart_id(request)
        return super().get(request, *args, **kwargs)


@method_decorator(xframe_options_exempt, 'dispatch')
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
