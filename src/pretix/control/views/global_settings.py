from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

from pretix.base.models import LogEntry, OrderPayment, OrderRefund
from pretix.base.services.update_check import check_result_table, update_check
from pretix.base.settings import GlobalSettingsObject
from pretix.control.forms.global_settings import (
    GlobalSettingsForm, UpdateSettingsForm,
)
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, StaffMemberRequiredMixin,
)


class GlobalSettingsView(AdministratorPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_settings.html'
    form_class = GlobalSettingsForm

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes have not been saved, see below for errors.'))
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('control:global.settings')


class UpdateCheckView(StaffMemberRequiredMixin, FormView):
    template_name = 'pretixcontrol/global_update.html'
    form_class = UpdateSettingsForm

    def post(self, request, *args, **kwargs):
        if 'trigger' in request.POST:
            update_check.apply()
            return redirect(self.get_success_url())
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes have not been saved, see below for errors.'))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['gs'] = GlobalSettingsObject()
        ctx['gs'].settings.set('update_check_ack', True)
        ctx['tbl'] = check_result_table()
        return ctx

    def get_success_url(self):
        return reverse('control:global.update')


class MessageView(TemplateView):
    template_name = 'pretixcontrol/global_message.html'


class LogDetailView(AdministratorPermissionRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        le = get_object_or_404(LogEntry, pk=request.GET.get('pk'))
        return JsonResponse({'data': le.parsed_data})


class PaymentDetailView(AdministratorPermissionRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        p = get_object_or_404(OrderPayment, pk=request.GET.get('pk'))
        return JsonResponse({'data': p.info_data})


class RefundDetailView(AdministratorPermissionRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        p = get_object_or_404(OrderRefund, pk=request.GET.get('pk'))
        return JsonResponse({'data': p.info_data})
