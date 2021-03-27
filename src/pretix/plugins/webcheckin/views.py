from django.views.generic import TemplateView

from pretix.control.permissions import EventPermissionRequiredMixin


class IndexView(EventPermissionRequiredMixin, TemplateView):
    permission = ('can_change_orders', 'can_checkin_orders')
    template_name = 'pretixplugins/webcheckin/index.html'
