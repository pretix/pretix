from django.db.models import Count
from django.views.generic import TemplateView


class EventViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = self.request.event
        return context


class EventIndex(EventViewMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch all items
        items = self.request.event.items.all().select_related(
            'category',
        ).annotate(quotac=Count('quotas')).filter(
            quotac__gt=0
        ).order_by('category__position', 'category_id', 'name')

        for item in items:
            item.available_variations = item.get_all_available_variations()
            item.has_variations = (len(item.available_variations) != 1
                                   or not item.available_variations[0].empty())

        # Regroup those by category
        context['items_by_category'] = sorted([
            (cat, [i for i in items if i.category_id == cat.identity])
            for cat in set([i.category for i in items])
        ], key=lambda group: group[0].position)
        return context
