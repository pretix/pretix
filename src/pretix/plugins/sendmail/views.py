import logging
from datetime import timedelta
import pytz

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView

from pretix.base.i18n import language
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

        tz = pytz.timezone(self.request.event.settings.timezone)

        failures = []
        self.output = {}
        for o in orders:
            if self.request.POST.get("action") == "preview":
                for l in self.request.event.settings.locales:
                    with language(l):
                        self.output[l] = []
                        self.output[l].append(_('Subject: {subject}').format(subject=form.cleaned_data['subject'].localize(l)))
                        message = form.cleaned_data['message'].localize(l)
                        preview_text = message.format(
                            order='ORDER1234',
                            event=self.request.event.name,
                            order_date=date_format(now(), 'SHORT_DATE_FORMAT'),
                            due_date=date_format(now() + timedelta(days=7), 'SHORT_DATE_FORMAT'),
                            order_url='link_to_order_url')
                        self.output[l].append(preview_text)
                return self.get(self.request, *self.args, **self.kwargs)
            else:
                try:
                    with language(o.locale):
                        mail(o.email, form.cleaned_data['subject'], form.cleaned_data['message'],
                             {
                                 'event': o.event,
                                 'order': o.code,
                                 'order_date': date_format(o.datetime.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                                 'due_date': date_format(o.expires, 'SHORT_DATE_FORMAT'),
                                 'order_url': build_absolute_uri(o.event, 'presale:event.order', kwargs={
                                     'order': 'ORDER1234',
                                     'secret': 'longrandomsecretabcdef123456'
                                 })},
                             self.request.event, locale=o.locale, order=o)
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

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx['output'] = getattr(self, 'output', None)
        return ctx
