from datetime import timedelta
import uuid

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.utils.timezone import now
from django.views.generic import View
from django.utils.translation import ugettext_lazy as _

from .event import EventViewMixin
from pretixbase.models import Item, ItemVariation, Quota, CartPosition


class CartActionMixin:

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

    def get_session_key(self):
        if 'cart_key' in self.request.session:
            return self.request.session.get('cart_key')
        key = str(uuid.uuid4())
        self.request.session['cart_key'] = key
        return key


class CartAdd(EventViewMixin, CartActionMixin, View):

    def post(self, *args, **kwargs):
        # Parse input
        items = []
        for key, value in self.request.POST.items():
            if value.strip() == '':
                continue
            if key.startswith('item_'):
                try:
                    items.append((key.split("_")[1], None, int(value)))
                except ValueError:
                    messages.error(self.request, _('Please only enter numbers.'))
                    return redirect(self.get_failure_url())
            elif key.startswith('variation_'):
                try:
                    items.append((key.split("_")[1], key.split("_")[2], int(value)))
                except ValueError:
                    messages.error(self.request, _('Please only enter numbers.'))
                    return redirect(self.get_failure_url())

        if sum(i[2] for i in items) > self.request.event.max_items_per_order:
            # TODO: Plurals
            messages.error(self.request,
                           _("You cannot select more than %d items per order") % self.event.max_items_per_order)
            return redirect(self.get_failure_url())

        # items is now a list of tuples of the form
        # (item id, variation id or None, number)

        # Fetch items from the database
        items_cache = {
            i.identity: i for i
            in Item.objects.filter(
                event=self.request.event,
                id__in=[i[0] for i in items]
            ).prefetch_related("quotas")
        }
        variations_cache = {
            v.identity: v for v
            in ItemVariation.objects.filter(
                item__event=self.request.event,
                id__in=[i[1] for i in items if i[1] is not None]
            ).select_related("item", "item__event").prefetch_related("quotas", "values", "values__prop")
        }

        # Process the request itself
        msg_some_unavailable = False
        for i in items:
            if i[0] not in items_cache or (i[1] is not None and i[1] not in variations_cache):
                messages.error(self.request, _('You selected an item which is not available for sale.'))
                return redirect(self.get_failure_url())
            item = items_cache[i[0]]
            variation = variations_cache[i[1]] if i[1] is not None else None
            price = item.execute_restrictions() if variation is None else variation.execute_restrictions()

            if price is False:
                msg_some_unavailable = True
                messages.error(self.request,
                               _('Some of the items you selected were no longer available. '
                                 'Please see below for details.'))
                continue

            quotas = list(item.quotas.all()) if variation is None else list(variation.quotas.all())
            quota_ok = i[2]
            try:
                for quota in quotas:
                    quota.lock()
                    avail = quota.availability()
                    if avail[0] != Quota.AVAILABILITY_OK:
                        if not msg_some_unavailable:
                            msg_some_unavailable = True
                            messages.error(self.request,
                                           _('Some of the items you selected were no longer available. '
                                             'Please see below for details.'))
                        quota_ok = 0
                        break
                    elif avail[1] < i[2]:
                        if not msg_some_unavailable:
                            msg_some_unavailable = True
                            messages.error(self.request,
                                           _('Some of the items you selected were no longer available in '
                                             'the quantity you selected. Please see below for details.'))
                        quota_ok = min(quota_ok, avail[1])

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
            finally:
                for quota in quotas:
                    quota.release()

        if not msg_some_unavailable:
            messages.success(self.request, _('The items have been successfully added to your cart.'))

        return redirect(self.get_success_url())
