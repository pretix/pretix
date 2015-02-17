from datetime import timedelta
import json

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.shortcuts import redirect
from django.utils.timezone import now
from django.views.generic import View
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Item, ItemVariation, Quota, CartPosition
from pretix.presale.views import EventLoginRequiredMixin, EventViewMixin


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
                    return False
            elif key.startswith('variation_'):
                try:
                    items.append((key.split("_")[1], key.split("_")[2], int(value)))
                except ValueError:
                    messages.error(self.request, _('Please enter numbers only.'))
                    return False
        if len(items) == 0:
            messages.warning(self.request, _('You did not select any items.'))
            return False
        return items

    def _re_add_position(self, items, position):
        for i, tup in enumerate(items):
            if tup[0] == position.item_id and tup[1] == position.variation_id:
                items[i] = (tup[0], tup[1], tup[2] + 1)
                return items
        items.append((position.item_id, position.variation_id, 1))
        return items


class CartRemove(EventViewMixin, CartActionMixin, EventLoginRequiredMixin, View):

    def post(self, *args, **kwargs):
        items = self._items_from_post_data()
        if not items:
            return redirect(self.get_failure_url())
        qw = Q(user=self.request.user)

        for item, variation, cnt in items:
            cw = qw & Q(item_id=item)
            if variation:
                cw &= Q(variation_id=variation)
            else:
                cw &= Q(variation__isnull=True)
            for cp in CartPosition.objects.current.filter(cw).order_by("-price")[:cnt]:
                cp.delete()

        messages.success(self.request, _('Your cart has been updated.'))
        return redirect(self.get_success_url())


class CartAdd(EventViewMixin, CartActionMixin, View):

    def post(self, request, *args, **kwargs):
        items = self._items_from_post_data()

        # We do not use EventLoginRequiredMixin here, as we want to store stuff into the
        # session beforehand
        if not request.user.is_authenticated() or \
                (request.user.event is None or request.user.event == request.event):
            request.session['cart_tmp'] = json.dumps(items)
            return redirect_to_login(
                request.path, reverse('presale:event.checkout.login', kwargs={
                    'organizer': request.event.organizer.slug,
                    'event': request.event.slug,
                }), 'next'
            )
        return self.process(items)

    def process(self, items):
        if not items:
            return redirect(self.get_failure_url())
        existing = CartPosition.objects.current.filter(user=self.request.user, event=self.request.event).count()
        if sum(i[2] for i in items) + existing > self.request.event.max_items_per_order:
            # TODO: i18n plurals
            messages.error(self.request,
                           _("You cannot select more than %d items per order") % self.event.max_items_per_order)
            return redirect(self.get_failure_url())

        # Extend this user's cart session to 30 minutes from now to ensure all items in the
        # cart expire at the same
        # We can extend the reservation of items which are not yet expired without
        # risk
        CartPosition.objects.current.filter(
            Q(user=self.request.user) & Q(event=self.request.event) & Q(expires__gt=now())
        ).update(expires=now() + timedelta(minutes=30))

        # For items that are already expired, we have to delete and re-add them, as they might
        # be no longer available. Sorry!
        for cp in CartPosition.objects.current.filter(
                Q(user=self.request.user) & Q(event=self.request.event) & Q(expires__lte=now())):
            items = self._re_add_position(items, cp)
            cp.delete()

        # Fetch items from the database
        items_cache = {
            i.identity: i for i
            in Item.objects.current.filter(
                event=self.request.event,
                identity__in=[i[0] for i in items]
            ).prefetch_related("quotas")
        }
        variations_cache = {
            v.identity: v for v
            in ItemVariation.objects.current.filter(
                item__event=self.request.event,
                identity__in=[i[1] for i in items if i[1] is not None]
            ).select_related("item", "item__event").prefetch_related("quotas", "values", "values__prop")
        }

        # Process the request itself
        msg_some_unavailable = False
        for i in items:
            # Check whether the specified items are part of what we just fetched from the database
            # If they are not, the user supplied item IDs which either do not exist or belong to
            # a different event
            if i[0] not in items_cache or (i[1] is not None and i[1] not in variations_cache):
                messages.error(self.request, _('You selected an item which is not available for sale.'))
                return redirect(self.get_failure_url())

            item = items_cache[i[0]]
            variation = variations_cache[i[1]] if i[1] is not None else None

            # Execute restriction plugins to check whether they (a) change the price or
            # (b) make the item/variation unavailable. If neither is the case, check_restriction
            # will correctly return the default price
            price = item.check_restrictions() if variation is None else variation.check_restrictions()
            if price is False:
                if not msg_some_unavailable:
                    msg_some_unavailable = True
                    messages.error(self.request,
                                   _('Some of the items you selected were no longer available. '
                                     'Please see below for details.'))
                continue

            # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.
            quotas = list(item.quotas.all()) if variation is None else list(variation.quotas.all())
            if len(quotas) == 0:
                if not msg_some_unavailable:
                    msg_some_unavailable = True
                    messages.error(self.request,
                                   _('Some of the items you selected were no longer available. '
                                     'Please see below for details.'))
                continue

            # Assume that all quotas allow us to buy i[2] instances of the object
            quota_ok = i[2]
            try:
                for quota in quotas:
                    # Lock the quota, so no other thread is allowed to perform sales covered by this
                    # quota while we're doing so.
                    quota.lock()
                    avail = quota.availability()
                    if avail[0] != Quota.AVAILABILITY_OK:
                        # This quota is sold out/currently unavailable, so do not sell this at all
                        if not msg_some_unavailable:
                            msg_some_unavailable = True
                            messages.error(self.request,
                                           _('Some of the items you selected were no longer available. '
                                             'Please see below for details.'))
                        quota_ok = 0
                        break
                    elif avail[1] < i[2]:
                        # This quota is available, but with less than i[2] items left, so we have to
                        # reduce the number of bought items
                        if not msg_some_unavailable:
                            msg_some_unavailable = True
                            messages.error(self.request,
                                           _('Some of the items you selected were no longer available in '
                                             'the quantity you selected. Please see below for details.'))
                        quota_ok = min(quota_ok, avail[1])

                # Create a CartPosition for as much items as we can
                for k in range(quota_ok):
                    CartPosition.objects.create(
                        event=self.request.event,
                        user=self.request.user,
                        item=item,
                        variation=variation,
                        price=price,
                        expires=now() + timedelta(minutes=30)
                    )
            except Quota.LockTimeoutException:
                # Is raised when there are too many threads asking for quota locks and we were
                # unaible to get one
                if not msg_some_unavailable:
                    msg_some_unavailable = True
                    messages.error(self.request,
                                   _('We were not able to process your request completely as the '
                                     'server was too busy. Please try again.'))
            finally:
                # Release the locks. This is important ;)
                for quota in quotas:
                    quota.release()

        if not msg_some_unavailable:
            messages.success(self.request, _('The items have been successfully added to your cart.'))

        return redirect(self.get_success_url())

    def get(self, request, *args, **kwargs):
        if 'cart_tmp' in request.session and request.user.is_authenticated():
            items = json.loads(request.session['cart_tmp'])
            del request.session['cart_tmp']
            return self.process(items)
        return redirect(self.get_failure_url())
