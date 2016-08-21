import sys

from django.db.models import Count, Q
from django.utils.timezone import now
from django.views.generic import TemplateView

from . import CartMixin, EventViewMixin


def item_group_by_category(items):
    return sorted(
        [
            # a group is a tuple of a category and a list of items
            (cat, [i for i in items if i.category == cat])
            for cat in set([i.category for i in items])
            # insert categories into a set for uniqueness
            # a set is unsorted, so sort again by category
        ],
        key=lambda group: (group[0].position, group[0].id) if (
            group[0] is not None and group[0].id is not None) else (0, 0)
    )


class EventIndex(EventViewMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch all items
        items = self.request.event.items.all().filter(
            Q(active=True)
            & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
            & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
            & Q(hide_without_voucher=False)
        ).select_related(
            'category',  # for re-grouping
        ).prefetch_related(
            'quotas', 'variations__quotas', 'quotas__event'  # for .availability()
        ).annotate(quotac=Count('quotas')).filter(
            quotac__gt=0
        ).order_by('category__position', 'category_id', 'position', 'name')
        
        display_add_to_cart = False
        for item in items:
            item.available_variations = list(item.variations.filter(active=True, quotas__isnull=False).distinct())
            item.has_variations = item.variations.exists()
            if not item.has_variations:
                item.cached_availability = list(item.check_quotas())
                item.order_max = min(item.cached_availability[1]
                                     if item.cached_availability[1] is not None else sys.maxsize,
                                     int(self.request.event.settings.max_items_per_order))
                item.price = item.default_price
                display_add_to_cart = item.order_max > 0
            else:
                for var in item.available_variations:
                    var.cached_availability = list(var.check_quotas())
                    var.order_max = min(var.cached_availability[1]
                                        if var.cached_availability[1] is not None else sys.maxsize,
                                        int(self.request.event.settings.max_items_per_order))
                    display_add_to_cart = var.order_max > 0
                    var.price = var.default_price if var.default_price is not None else item.default_price
                if len(item.available_variations) > 0:
                    item.min_price = min([v.price for v in item.available_variations])
                    item.max_price = max([v.price for v in item.available_variations])


        items = [item for item in items if len(item.available_variations) > 0 or not item.has_variations]

        # Regroup those by category
        context['items_by_category'] = item_group_by_category(items)
        context['display_add_to_cart'] = display_add_to_cart

        vouchers_exist = self.request.event.get_cache().get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.get_cache().set('vouchers_exist', vouchers_exist)
        context['vouchers_exist'] = vouchers_exist

        context['cart'] = self.get_cart()
        context['frontpage_text'] = str(self.request.event.settings.frontpage_text)
        return context
