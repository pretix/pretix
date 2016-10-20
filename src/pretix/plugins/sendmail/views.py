import logging

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView

from pretix.base.models import Order
from pretix.base.services.mail import SendMailException, mail
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.multidomain.urlreverse import build_absolute_uri

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
        qs = Order.objects.filter(event=self.request.event)
        statusq = Q(status__in=form.cleaned_data['sendto'])
        if 'overdue' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, expires__lt=now())
        orders = qs.filter(statusq)

        self.request.event.log_action('pretix.plugins.sendmail.sent', user=self.request.user, data=dict(
            form.cleaned_data))

        failures = []
        for o in orders:
            try:
                mail(o.email, form.cleaned_data['subject'], form.cleaned_data['message'],
                     {
                         'event': o.event,
                         'order': o.code,
                         'order_date': date_format(o.datetime, 'SHORT_DATETIME_FORMAT'),
                         'due_date': date_format(o.expires, 'SHORT_DATE_FORMAT'),
                         'order_url': build_absolute_uri(o.event, 'presale:event.order', kwargs={
                             'order': o.code,
                             'secret': o.secret
                         })
                }, self.request.event, locale=o.locale, order=o)
            except SendMailException:
                failures.append(o.email)

        if failures:
            messages.error(self.request, _('Failed to send mails to the following users: {}'.format(' '.join(failures))))
        else:
            messages.success(self.request, _('Your message has been queued to be sent to the selected users.'))

        return redirect(
            'plugins:sendmail:send',
            event=self.request.event.slug,
            organizer=self.request.event.organizer.slug
        )
