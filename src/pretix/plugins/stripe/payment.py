import json
import logging
from collections import OrderedDict

import stripe
from django import forms
from django.contrib import messages
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Quota, RequiredAction
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.multidomain.urlreverse import build_absolute_uri

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
                 )),
                ('ui',
                 forms.ChoiceField(
                     label=_('User interface'),
                     choices=(
                         ('pretix', _('Simple (pretix design)')),
                         ('checkout', _('Stripe Checkout')),
                     )
                 ))
            ]
        )

    def settings_content_render(self, request):
        return "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
            _('Please configure a <a href="https://dashboard.stripe.com/account/webhooks">Stripe Webhook</a> to '
              'the following endpoint in order to automatically cancel orders when charges are refunded externally.'),
            build_absolute_uri(self.event, 'plugins:stripe:webhook')
        )

    def payment_is_valid_session(self, request):
        return request.session.get('payment_stripe_token', '') != ''

    def order_prepare(self, request, order):
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
        ui = self.settings.get('ui', default='pretix')
        if ui == 'checkout':
            template = get_template('pretixplugins/stripe/checkout_payment_form_stripe_checkout.html')
        else:
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
        return self._is_still_available()

    def payment_perform(self, request, order) -> str:
        self._init_api()
        try:
            charge = stripe.Charge.create(
                amount=int(order.total * 100),
                currency=self.event.currency.lower(),
                source=request.session['payment_stripe_token'],
                metadata={
                    'order': str(order.id),
                    'event': self.event.id,
                    'code': order.code
                },
                # TODO: Is this sufficient?
                idempotency_key=str(self.event.id) + order.code + request.session['payment_stripe_token']
            )
        except stripe.error.CardError as e:
            if e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            logger.info('Stripe card error: %s' % str(err))
            order.payment_info = json.dumps({
                'error': True,
                'message': err['message'],
            })
            order.save()
            raise PaymentException(_('Stripe reported an error with your card: %s') % err['message'])

        except stripe.error.StripeError as e:
            if e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            order.payment_info = json.dumps({
                'error': True,
                'message': err['message'],
            })
            order.save()
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))
        else:
            if charge.status == 'succeeded' and charge.paid:
                try:
                    mark_order_paid(order, 'stripe', str(charge))
                except Quota.QuotaExceededException as e:
                    RequiredAction.objects.create(
                        event=request.event, action_type='pretix.plugins.stripe.overpaid', data=json.dumps({
                            'order': order.code,
                            'charge': charge.id
                        })
                    )
                    raise PaymentException(str(e))

                except SendMailException:
                    raise PaymentException(_('There was an error sending the confirmation mail.'))
            else:
                logger.info('Charge failed: %s' % str(charge))
                order.payment_info = str(charge)
                order.save()
                raise PaymentException(_('Stripe reported an error: %s') % charge.failure_message)
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
        except (stripe.error.InvalidRequestError, stripe.error.AuthenticationError, stripe.error.APIConnectionError) \
                as e:
            if e.json_body:
                err = e.json_body['error']
                logger.exception('Stripe error: %s' % str(err))
            else:
                err = {'message': str(e)}
                logger.exception('Stripe error: %s' % str(e))
            messages.error(request, _('We had trouble communicating with Stripe. Please try again and contact '
                                      'support if the problem persists.'))
            logger.error('Stripe error: %s' % str(err))
        except stripe.error.StripeError:
            mark_order_refunded(order, user=request.user)
            messages.warning(request, _('We were unable to transfer the money back automatically. '
                                        'Please get in touch with the customer and transfer it back manually.'))
        else:
            order = mark_order_refunded(order, user=request.user)
            order.payment_info = str(ch)
            order.save()
