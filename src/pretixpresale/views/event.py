from django.views.generic import TemplateView


class EventIndex(TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = self.request.event
        return context
