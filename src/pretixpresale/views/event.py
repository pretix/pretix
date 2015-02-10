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
        items = self.request.event.items.all().select_related(
            'category'
        ).order_by('category__position', 'category_id', 'name')
        # Regroup those by category
        context['items_by_category'] = [
            (cat, [i for i in items if i.category_id == cat.identity])
            for cat in set([i.category for i in items])
        ]
        return context
