from collections import OrderedDict
import json
import logging
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext as __
from django import forms

import paypalrestsdk

from pretix.base.payment import BasePaymentProvider


logger = logging.getLogger('pretix.plugins.paypal')


class Paypal(BasePaymentProvider):

    identifier = 'paypal'
    verbose_name = _('PayPal')
    checkout_form_fields = OrderedDict([
    ])

    @property
    def settings_form_fields(self):
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('endpoint',
                 forms.ChoiceField(
                     label=_('Endpoint'),
                     initial='live',
                     choices=(
                         ('live', 'Live'),
                         ('sandbox', 'Sandbox'),
                     ),
                     required=False
                 )),
                ('client_id',
                 forms.CharField(
                     label=_('Client ID'),
                     required=False
                 )),
                ('secret',
                 forms.CharField(
                     label=_('Secret'),
                     required=False
                 ))
            ]
        )

    def init_api(self):
        paypalrestsdk.set_config(
            mode="sandbox" if "sandbox" in self.settings.get('endpoint') else 'live',
            client_id=self.settings.get('client_id'),
            client_secret=self.settings.get('secret'))

    def checkout_is_valid_session(self, request):
        return (request.session.get('payment_paypal_id', '') != ''
                and request.session.get('payment_paypal_payer', '') != '')

    def checkout_form_render(self, request) -> str:
        template = get_template('pretixplugins/paypal/checkout_payment_form.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings})
        return template.render(ctx)

    def checkout_prepare(self, request, cart):
        self.init_api()
        items = []
        for cp in cart['positions']:
            items.append({
                "name": cp.item.name,
                "description": str(cp.variation) if cp.variation else "",
                "quantity": cp.count,
                "price": str(cp.price),
                "currency": request.event.currency
            })
        if cart['payment_fee']:
            items.append({
                "name": __('Payment method fee'),
                "description": "",
                "quantity": 1,
                "currency": request.event.currency,
                "price": str(cart['payment_fee'])
            })
        payment = paypalrestsdk.Payment({
            'intent': 'sale',
            'payer': {
                "payment_method": "paypal",
            },
            "redirect_urls": {
                "return_url": request.build_absolute_uri(reverse('plugins:paypal.return')),
                "cancel_url": request.build_absolute_uri(reverse('plugins:paypal.abort')),
            },
            "transactions": [
                {
                    "item_list": {
                        "items": items
                    },
                    "amount": {
                        "currency": request.event.currency,
                        "total": str(cart['total'])
                    },
                    "description": __('Event tickets for %s') % request.event.name
                }
            ]
        })
        return self._create_payment(request, payment)

    def _create_payment(self, request, payment):
        if payment.create():
            if payment.state not in ('created', 'approved', 'pending'):
                messages.error(request, _('We had trouble communicating with PayPal'))
                logger.error('Invalid payment state: ' + str(payment))
                return
            request.session['payment_paypal_id'] = payment.id
            request.session['payment_paypal_event'] = self.event.id
            for link in payment.links:
                if link.method == "REDIRECT" and link.rel == "approval_url":
                    return str(link.href)
        else:
            messages.error(request, _('We had trouble communicating with PayPal'))
            logger.error('Error on creating payment: ' + str(payment.error))

    def checkout_confirm_render(self, request) -> str:
        """
        Returns the HTML that should be displayed when the user selected this provider
        on the 'confirm order' page.
        """
        template = get_template('pretixplugins/paypal/checkout_payment_confirm.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings})
        return template.render(ctx)

    def checkout_perform(self, request, order) -> str:
        """
        Will be called if the user submitted his order successfully to initiate the
        payment process.

        It should return a custom redirct URL, if you need special behaviour, or None to
        continue with default behaviour.

        On errors, it should use Django's message framework to display an error message
        to the user (or the normal form validation error messages).

        :param order: The order object
        """
        if (request.session.get('payment_paypal_id', '') == ''
                or request.session.get('payment_paypal_payer', '') == ''):
            messages.error(request, _('We were unable to process your payment. See below for details on how to '
                                      'proceed.'))

        self.init_api()
        payment = paypalrestsdk.Payment.find(request.session.get('payment_paypal_id'))
        if str(payment.transactions[0].amount.total) != str(order.total) or payment.transactions[0].amount.currency != \
                self.event.currency:
            messages.error(request, _('We were unable to process your payment. See below for details on how to '
                                      'proceed.'))
            logger.error('Value mismatch: Order %s vs payment %s' % (order.id, str(payment)))
            return

        return self._execute_payment(payment, request, order)

    def _execute_payment(self, payment, request, order):
        payment.execute({"payer_id": request.session.get('payment_paypal_payer')})

        if payment.state == 'pending':
            messages.warning(request, _('PayPal has not yet approved the payment. We will inform you as soon as the '
                                        'payment completed.'))
            order = order.clone()
            order.payment_info = json.dumps(payment.to_dict())
            order.save()
            return

        if payment.state != 'approved':
            messages.error(request, _('We were unable to process your payment. See below for details on how to '
                                      'proceed.'))
            logger.error('Invalid state: %s' % str(payment))
            return

        order.mark_paid('paypal', json.dumps(payment.to_dict()))
        messages.success(request, _('We successfully received your payment. Thank you!'))
        return None

    def order_pending_render(self, request, order) -> str:
        retry = True
        try:
            if order.payment_info and json.loads(order.payment_info)['state'] != 'pending':
                retry = False
        except KeyError:
            pass
        template = get_template('pretixplugins/paypal/pending.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings,
                       'retry': retry, 'order': order})
        return template.render(ctx)

    def order_control_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
        else:
            payment_info = None
        template = get_template('pretixplugins/paypal/control.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings,
                       'payment_info': payment_info, 'order': order})
        return template.render(ctx)
