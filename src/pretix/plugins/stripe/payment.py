import json
import logging
from collections import OrderedDict

import stripe
from django import forms
from django.contrib import messages
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Quota
from pretix.base.payment import BasePaymentProvider
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.helpers.urls import build_absolute_uri

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
                 )),
                ('publishable_key',
                 forms.CharField(
                     label=_('Publishable key'),
                 ))
            ]
        )

    def settings_content_render(self, request):
        return "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
            _('Please configure a <a href="https://dashboard.stripe.com/account/webhooks">Stripe Webhook</a> to '
              'the following endpoint in order to automatically cancel orders when a charges are refunded externally.'),
            build_absolute_uri('plugins:stripe:webhook')
        )

    def payment_is_valid_session(self, request):
        return request.session.get('payment_stripe_token') != ''

    def retry_prepare(self, request, order):
        return self.checkout_prepare(request, None)

    def checkout_prepare(self, request, cart):
        token = request.POST.get('stripe_token', '')
        request.session['payment_stripe_token'] = token
        request.session['payment_stripe_brand'] = request.POST.get('stripe_card_brand', '')
        request.session['payment_stripe_last4'] = request.POST.get('stripe_card_last4', '')
        if token == '':
            messages.error(request, _('You may need to enable JavaScript for Stripe payments.'))
            return False
        return True

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def _init_api(self):
        stripe.api_version = '2015-04-07'
        stripe.api_key = self.settings.get('secret_key')

    def checkout_confirm_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def order_can_retry(self, order):
        return True

    def payment_perform(self, request, order) -> str:
        self._init_api()
        try:
            charge = stripe.Charge.create(
                amount=int(order.total * 100),
                currency=request.event.currency.lower(),
                source=request.session['payment_stripe_token'],
                metadata={
                    'order': order.id,
                    'event': self.event.id,
                    'code': order.code
                },
                # TODO: Is this sufficient?
                idempotency_key=self.event.id + order.code + request.session['payment_stripe_token']
            )
        except stripe.error.CardError as e:
            err = e.json_body['error']
            messages.error(request, _('Stripe reported an error with your card: %s' % err['message']))
            logger.info('Stripe card error: %s' % str(err))
            order.payment_info = json.dumps({
                'error': True,
                'message': err['message'],
            })
            order.save()
        except stripe.error.InvalidRequestError or stripe.error.AuthenticationError or stripe.error.APIConnectionError \
                or stripe.error.StripeError as e:
            err = e.json_body['error']
            messages.error(request, _('We had trouble communicating with Stripe. Please try again and get in touch '
                                      'with us if this problem persists.'))
            logger.error('Stripe error: %s' % str(err))
            order.payment_info = json.dumps({
                'error': True,
                'message': err['message'],
            })
            order.save()
        else:
            if charge.status == 'succeeded' and charge.paid:
                try:
                    mark_order_paid(order, 'stripe', str(charge))
                except Quota.QuotaExceededException as e:
                    messages.error(request, str(e))
            else:
                messages.warning(request, _('Stripe reported an error: %s' % charge.failure_message))
                logger.info('Charge failed: %s' % str(charge))
                order.payment_info = str(charge)
                order.save()
        del request.session['payment_stripe_token']

    def order_pending_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
        else:
            payment_info = None
        template = get_template('pretixplugins/stripe/pending.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'order': order, 'payment_info': payment_info}
        return template.render(ctx)

    def order_control_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
            if 'amount' in payment_info:
                payment_info['amount'] /= 100
        else:
            payment_info = None
        template = get_template('pretixplugins/stripe/control.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'payment_info': payment_info, 'order': order}
        return template.render(ctx)

    def order_control_refund_render(self, order) -> str:
        return '<div class="alert alert-info">%s</div>' % _('The money will be automatically refunded.')

    def order_control_refund_perform(self, request, order) -> "bool|str":
        self._init_api()

        if order.payment_info:
            payment_info = json.loads(order.payment_info)
        else:
            payment_info = None

        if not payment_info:
            mark_order_refunded(order, user=request.user)
            messages.warning(request, _('We were unable to transfer the money back automatically. '
                                        'Please get in touch with the customer and transfer it back manually.'))
            return

        try:
            ch = stripe.Charge.retrieve(payment_info['id'])
            ch.refunds.create()
            ch.refresh()
        except stripe.error.InvalidRequestError or stripe.error.AuthenticationError or stripe.error.APIConnectionError \
                as e:
            err = e.json_body['error']
            messages.error(request, _('We had trouble communicating with Stripe. Please try again and contact '
                                      'support if the problem persists.'))
            logger.error('Stripe error: %s' % str(err))
        except stripe.error.StripeError:
            mark_order_refunded(order)
            messages.warning(request, _('We were unable to transfer the money back automatically. '
                                        'Please get in touch with the customer and transfer it back manually.'))
        else:
            order = mark_order_refunded(order)
            order.payment_info = str(ch)
            order.save()
