from datetime import timedelta

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.shortcuts import redirect
from django.utils.timezone import now
from django.views.generic import View
from django.utils.translation import ugettext_lazy as _

from pretixbase.models import Item, ItemVariation, Quota, CartPosition
from pretixpresale.views import CartMixin, EventViewMixin


class CartActionMixin(CartMixin):

    def get_next_url(self):
        if "next" in self.request.GET and '://' not in self.request.GET:
            return self.request.GET.get('next')
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


class CartRemove(EventViewMixin, CartActionMixin, View):

    def post(self, *args, **kwargs):
        items = self._items_from_post_data()
        if not items:
            return redirect(self.get_failure_url())
        qw = Q(session=self.get_session_key())
        if self.request.user.is_authenticated():
            qw |= Q(user=self.request.user)

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

    def post(self, *args, **kwargs):
        items = self._items_from_post_data()
        if not items:
            return redirect(self.get_failure_url())

        if sum(i[2] for i in items) > self.request.event.max_items_per_order:
            # TODO: i18n plurals
            messages.error(self.request,
                           _("You cannot select more than %d items per order") % self.event.max_items_per_order)
            return redirect(self.get_failure_url())

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

        # Extend this user's cart session to 30 minutes from now to ensure all items in the
        # cart expire at the same time
        qw = Q(session=self.get_session_key())
        if self.request.user.is_authenticated():
            qw |= Q(user=self.request.user)
        CartPosition.objects.current.filter(
            qw & Q(event=self.request.event)).update(expires=now() + timedelta(minutes=30))

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
                        session=self.get_session_key(),
                        user=(self.request.user if self.request.user.is_authenticated() else None),
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
