from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.views.generic import View, ListView
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Event, Order, LogEntry
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views.event import EventSettingsFormView
from .forms import ZaloZNSSettingsForm
from .tasks import send_zns

class ZaloZNSSettings(EventSettingsFormView):
    model = Event
    form_class = ZaloZNSSettingsForm
    template_name = 'pretixplugins/zalozns/settings.html'
    permission = 'can_change_event_settings'

    def get_success_url(self, **kwargs):
        return reverse('plugins:zalozns:settings', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

class ZaloZNSSendView(EventPermissionRequiredMixin, View):
    permission = 'can_change_orders'

    def post(self, request, *args, **kwargs):
        order = get_object_or_404(Order, pk=kwargs.get('order'), event=self.request.event)
        send_zns.apply_async(args=[order.pk])
        messages.success(request, _('Zalo ZNS message has been queued for sending.'))
        return redirect('control:event.order', event=self.request.event.slug, organizer=self.request.event.organizer.slug, code=order.code)

class ZaloZNSHistoryView(EventPermissionRequiredMixin, ListView):
    model = LogEntry
    template_name = 'pretixplugins/zalozns/history.html'
    permission = 'can_view_orders'
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):
        return LogEntry.objects.filter(
            event=self.request.event,
            action_type__startswith='pretix.plugins.zalozns'
        ).select_related('order').order_by('-datetime')
