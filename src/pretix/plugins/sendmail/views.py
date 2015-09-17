import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView

from pretix.base.models import Order
from pretix.base.services.mail import mail
from pretix.control.permissions import EventPermissionRequiredMixin

from . import forms

logger = logging.getLogger('pretix.plugins.sendmail')


class SenderView(EventPermissionRequiredMixin, FormView):
    template_name = 'pretixplugins/sendmail/send_form.html'
    permission = 'can_change_orders'
    form_class = forms.MailForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        return kwargs

    def form_valid(self, form):
        orders = Order.objects.current.filter(
            event=self.request.event, status__in=form.cleaned_data['sendto']
        ).select_related("user")
        users = set([o.user for o in orders])

        for u in users:
            mail(u.email, form.cleaned_data['subject'], form.cleaned_data['message'],
                 None, self.request.event, locale=u.locale)

        messages.success(self.request, _('Your message will be sent to the selected users.'))

        return redirect(
            'plugins:sendmail:send',
            event=self.request.event.slug,
            organizer=self.request.event.organizer.slug
        )
