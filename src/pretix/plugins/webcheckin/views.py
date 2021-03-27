from django.views.generic import TemplateView

from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.countries import CachedCountries


class IndexView(EventPermissionRequiredMixin, TemplateView):
    permission = ('can_change_orders', 'can_checkin_orders')
    template_name = 'pretixplugins/webcheckin/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['countries'] = [
            {
                'key': key,
                'value': name
            }
            for key, name in CachedCountries()
        ]
        return ctx
