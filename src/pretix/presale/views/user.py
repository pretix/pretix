import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from pretix.base.email import get_email_context
from pretix.base.services.mail import INVALID_ADDRESS, SendMailException, mail
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.user import ResendLinkForm
from pretix.presale.views import EventViewMixin


class ResendLinkView(EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/resend_link.html'

    @cached_property
    def link_form(self):
        return ResendLinkForm(data=self.request.POST if self.request.method == 'POST' else None)

    def post(self, request, *args, **kwargs):
        if not self.link_form.is_valid():
            messages.error(self.request, _('We had difficulties processing your input.'))
            return self.get(request, *args, **kwargs)

        user = self.link_form.cleaned_data.get('email')

        if settings.HAS_REDIS:
            from django_redis import get_redis_connection
            rc = get_redis_connection("redis")
            if rc.exists('pretix_resend_{}_{}'.format(request.event.pk, user)):
                messages.error(request, _('If the email address you entered is valid and associated with a ticket, we have '
                                          'already sent you an email with a link to your ticket in the past {number} hours. '
                                          'If the email did not arrive, please your check spam folder and also double check '
                                          'that you used the correct email address.').format(number=24))
                return redirect(eventreverse(self.request.event, 'presale:event.resend_link'))
            else:
                rc.setex('pretix_resend_{}_{}'.format(request.event.pk, user), 3600 * 24, '1')

        orders = self.request.event.orders.filter(email__iexact=user)

        if not orders:
            user = INVALID_ADDRESS

        subject = _('Your orders for {}').format(self.request.event)
        template = self.request.event.settings.mail_text_resend_all_links
        context = get_email_context(event=self.request.event, orders=orders)
        try:
            mail(user, subject, template, context, event=self.request.event, locale=self.request.LANGUAGE_CODE)
        except SendMailException:
            logger = logging.getLogger('pretix.presale.user')
            logger.exception('A mail resending order links to {} could not be sent.'.format(user))
            messages.error(self.request, _('We have trouble sending emails right now, please check back later.'))
            return self.get(request, *args, **kwargs)

        messages.success(self.request, _('If there were any orders by this user, they will receive an email with their order codes.'))
        return redirect(eventreverse(self.request.event, 'presale:event.index'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.link_form
        return context


class UnlockHashView(EventViewMixin, View):
    # Allows to register an unlock hash in the user's session, e.g. to unlock a hidden payment provider

    def get(self, request, *args, **kwargs):
        hashes = request.session.get('pretix_unlock_hashes', [])
        hashes.append(kwargs.get('hash'))
        request.session['pretix_unlock_hashes'] = hashes
        return redirect(eventreverse(self.request.event, 'presale:event.index'))
