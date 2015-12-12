import sys

from django.db.models import Q, Count
from django.utils.timezone import now
from django.views.generic import TemplateView

from pretix.presale.views import CartMixin, EventViewMixin


class EventIndex(EventViewMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch all items
        items = self.request.event.items.all().filter(
            Q(active=True)
            & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
            & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
        ).select_related(
            'category',  # for re-grouping
        ).prefetch_related(
            'properties',  # for .get_all_available_variations()
            'quotas', 'variations__quotas', 'quotas__event'  # for .availability()
        ).annotate(quotac=Count('quotas')).filter(
            quotac__gt=0
        ).order_by('category__position', 'category_id', 'position', 'name')

        for item in items:
            item.available_variations = sorted(item.get_all_available_variations(),
                                               key=lambda vd: vd.ordered_values())
            item.has_variations = (len(item.available_variations) != 1
                                   or not item.available_variations[0].empty())
            if not item.has_variations:
                item.cached_availability = list(item.check_quotas())
                item.cached_availability[1] = min((item.cached_availability[1]
                                                   if item.cached_availability[1] is not None else sys.maxsize),
                                                  int(self.request.event.settings.max_items_per_order))
                item.price = item.available_variations[0]['price']
            else:
                for var in item.available_variations:
                    var.cached_availability = list(var['variation'].check_quotas())
                    var.cached_availability[1] = min(var.cached_availability[1]
                                                     if var.cached_availability[1] is not None else sys.maxsize,
                                                     int(self.request.event.settings.max_items_per_order))
                    var.price = var.get('price', item.default_price)
                if len(item.available_variations) > 0:
                    item.min_price = min([v.price for v in item.available_variations])
                    item.max_price = max([v.price for v in item.available_variations])

        items = [item for item in items if len(item.available_variations) > 0]

        # Regroup those by category
        context['items_by_category'] = sorted(
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

        context['cart'] = self.get_cart()
        return context
