from collections import OrderedDict
import json
import logging
from django.contrib import messages
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from django import forms
import stripe

from pretix.base.payment import BasePaymentProvider

logger = logging.getLogger('pretix.plugins.stripe')


class Stripe(BasePaymentProvider):
    identifier = 'stripe'
    verbose_name = _('Credit Card via Stripe')

    @property
    def settings_form_fields(self):
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('secret_key',
                 forms.CharField(
                     label=_('Secret key'),
                     required=False
                 )),
                ('publishable_key',
                 forms.CharField(
                     label=_('Publishable key'),
                     required=False
                 ))
            ]
        )

    def checkout_is_valid_session(self, request):
        return request.session.get('payment_stripe_token') != ''

    def checkout_prepare(self, request, cart):
        token = request.POST.get('stripe_token', '')
        request.session['payment_stripe_token'] = token
        request.session['payment_stripe_brand'] = request.POST.get('stripe_card_brand', '')
        request.session['payment_stripe_last4'] = request.POST.get('stripe_card_last4', '')
        if token == '':
            messages.error(request, _('You may need to enable JavaScript for Stripe payments.'))
            return False
        return True

    def checkout_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings})
        return template.render(ctx)

    def _init_api(self):
        stripe.api_key = self.settings.get('secret_key')

    def checkout_confirm_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_confirm.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings})
        return template.render(ctx)

    def checkout_perform(self, request, order) -> str:
        self._init_api()
        charge = stripe.Charge.create(
            amount=int(order.total * 100),
            currency=request.event.currency.lower(),
            source=request.session['payment_stripe_token'],
            idempotency_key=self.event.identity + order.code  # TODO: Use something better
        )
        logging.info(charge)
        if charge.status == 'succeeded' and charge.paid:
            order.mark_paid('stripe', str(charge))
            messages.success(request, _('We successfully received your payment. Thank you!'))
        else:
            messages.warning(request, _('Stripe reported an error: %s' % charge.failure_message))
            order = order.clone()
            order.payment_info = str(charge)
            order.save()

    def order_pending_render(self, request, order) -> str:
        template = get_template('pretixplugins/stripe/pending.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings,
                       'order': order})
        return template.render(ctx)

    def order_control_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
            payment_info['amount'] /= 100
        else:
            payment_info = None
        template = get_template('pretixplugins/stripe/control.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings,
                       'payment_info': payment_info, 'order': order})
        return template.render(ctx)
