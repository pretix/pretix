import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView

from pretix.base.services.mail import INVALID_ADDRESS, SendMailException, mail
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
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
            if rc.exists('pretix_resend_{}'.format(user)):
                messages.error(request, _('We already sent you an email in the last 24 hours.'))
                return redirect(eventreverse(self.request.event, 'presale:event.resend_link'))
            else:
                rc.setex('pretix_resend_{}'.format(user), 3600 * 24, '1')

        orders = self.request.event.orders.filter(email__iexact=user)
        order_context = []

        for order in orders:
            url = build_absolute_uri(
                self.request.event,
                'presale:event.order',
                kwargs={'order': order.code, 'secret': order.secret}
            )
            order_context.append(' - {} - {}'.format(order, url))

        if not orders:
            user = INVALID_ADDRESS

        subject = _('Your orders for {}'.format(self.request.event))
        template = self.request.event.settings.mail_text_resend_all_links
        context = {
            'orders': '\n'.join(order_context),
            'event': self.request.event,
        }
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
