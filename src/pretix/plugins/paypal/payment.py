import json
import logging
import urllib.parse
from collections import OrderedDict

import paypalrestsdk
from django import forms
from django.contrib import messages
from django.core import signing
from django.template.loader import get_template
from django.utils.translation import ugettext as __, ugettext_lazy as _

from pretix.base.models import Order, Quota, RequiredAction
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.plugins.paypal.models import ReferencedPayPalObject

logger = logging.getLogger('pretix.plugins.paypal')


class RefundForm(forms.Form):
    auto_refund = forms.ChoiceField(
        initial='auto',
        label=_('Refund automatically?'),
        choices=(
            ('auto', _('Automatically refund charge with PayPal')),
            ('manual', _('Do not send refund instruction to PayPal, only mark as refunded in pretix'))
        ),
        widget=forms.RadioSelect,
    )


class Paypal(BasePaymentProvider):
    identifier = 'paypal'
    verbose_name = _('PayPal')
    payment_form_fields = OrderedDict([
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
                 )),
                ('client_id',
                 forms.CharField(
                     label=_('Client ID'),
                     max_length=80,
                     min_length=80,
                     help_text=_('<a target="_blank" rel="noopener" href="{docs_url}">{text}</a>').format(
                         text=_('Click here for a tutorial on how to obtain the required keys'),
                         docs_url='https://docs.pretix.eu/en/latest/user/payments/paypal.html'
                     )
                 )),
                ('secret',
                 forms.CharField(
                     label=_('Secret'),
                     max_length=80,
                     min_length=80,
                 ))
            ]
        )

    def settings_content_render(self, request):
        return "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
            _('Please configure a PayPal Webhook to the following endpoint in order to automatically cancel orders '
              'when payments are refunded externally.'),
            build_global_uri('plugins:paypal:webhook')
        )

    def init_api(self):
        paypalrestsdk.set_config(
            mode="sandbox" if "sandbox" in self.settings.get('endpoint') else 'live',
            client_id=self.settings.get('client_id'),
            client_secret=self.settings.get('secret'))

    def payment_is_valid_session(self, request):
        return (request.session.get('payment_paypal_id', '') != ''
                and request.session.get('payment_paypal_payer', '') != '')

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/paypal/checkout_payment_form.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def checkout_prepare(self, request, cart):
        self.init_api()
        kwargs = {}
        if request.resolver_match and 'cart_namespace' in request.resolver_match.kwargs:
            kwargs['cart_namespace'] = request.resolver_match.kwargs['cart_namespace']

        payment = paypalrestsdk.Payment({
            'intent': 'sale',
            'payer': {
                "payment_method": "paypal",
            },
            "redirect_urls": {
                "return_url": build_absolute_uri(request.event, 'plugins:paypal:return', kwargs=kwargs),
                "cancel_url": build_absolute_uri(request.event, 'plugins:paypal:abort', kwargs=kwargs),
            },
            "transactions": [
                {
                    "item_list": {
                        "items": [
                            {
                                "name": __('Order for %s') % str(request.event),
                                "quantity": 1,
                                "price": str(cart['total']),
                                "currency": request.event.currency
                            }
                        ]
                    },
                    "amount": {
                        "currency": request.event.currency,
                        "total": str(cart['total'])
                    },
                    "description": __('Event tickets for {event}').format(event=request.event.name)
                }
            ]
        })
        request.session['payment_paypal_order'] = None
        return self._create_payment(request, payment)

    def _create_payment(self, request, payment):
        try:
            if payment.create():
                if payment.state not in ('created', 'approved', 'pending'):
                    messages.error(request, _('We had trouble communicating with PayPal'))
                    logger.error('Invalid payment state: ' + str(payment))
                    return
                request.session['payment_paypal_id'] = payment.id
                for link in payment.links:
                    if link.method == "REDIRECT" and link.rel == "approval_url":
                        if request.session.get('iframe_session', False):
                            signer = signing.Signer(salt='safe-redirect')
                            return (
                                build_absolute_uri(request.event, 'plugins:paypal:redirect') + '?url=' +
                                urllib.parse.quote(signer.sign(link.href))
                            )
                        else:
                            return str(link.href)
            else:
                messages.error(request, _('We had trouble communicating with PayPal'))
                logger.error('Error on creating payment: ' + str(payment.error))
        except Exception as e:
            messages.error(request, _('We had trouble communicating with PayPal'))
            logger.error('Error on creating payment: ' + str(e))

    def checkout_confirm_render(self, request) -> str:
        """
        Returns the HTML that should be displayed when the user selected this provider
        on the 'confirm order' page.
        """
        template = get_template('pretixplugins/paypal/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def payment_perform(self, request, order) -> str:
        """
        Will be called if the user submitted his order successfully to initiate the
        payment process.

        It should return a custom redirct URL, if you need special behavior, or None to
        continue with default behavior.

        On errors, it should use Django's message framework to display an error message
        to the user (or the normal form validation error messages).

        :param order: The order object
        """
        if (request.session.get('payment_paypal_id', '') == ''
                or request.session.get('payment_paypal_payer', '') == ''):
            raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                     'proceed.'))

        self.init_api()
        payment = paypalrestsdk.Payment.find(request.session.get('payment_paypal_id'))
        ReferencedPayPalObject.objects.get_or_create(order=order, reference=payment.id)
        if str(payment.transactions[0].amount.total) != str(order.total) or payment.transactions[0].amount.currency != \
                self.event.currency:
            logger.error('Value mismatch: Order %s vs payment %s' % (order.id, str(payment)))
            raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                     'proceed.'))

        return self._execute_payment(payment, request, order)

    def _execute_payment(self, payment, request, order):
        if payment.state == 'created':
            payment.replace([
                {
                    "op": "replace",
                    "path": "/transactions/0/item_list",
                    "value": {
                        "items": [
                            {
                                "name": __('Order {slug}-{code}').format(slug=self.event.slug.upper(), code=order.code),
                                "quantity": 1,
                                "price": str(order.total),
                                "currency": order.event.currency
                            }
                        ]
                    }
                },
                {
                    "op": "replace",
                    "path": "/transactions/0/description",
                    "value": __('Order {order} for {event}').format(
                        event=request.event.name,
                        order=order.code
                    )
                }
            ])
            payment.execute({"payer_id": request.session.get('payment_paypal_payer')})

        order.refresh_from_db()
        if payment.state == 'pending':
            messages.warning(request, _('PayPal has not yet approved the payment. We will inform you as soon as the '
                                        'payment completed.'))
            order.payment_info = json.dumps(payment.to_dict())
            order.save()
            return

        if payment.state != 'approved':
            logger.error('Invalid state: %s' % str(payment))
            raise PaymentException(_('We were unable to process your payment. See below for details on how to '
                                     'proceed.'))

        if order.status == Order.STATUS_PAID:
            logger.warning('PayPal success event even though order is already marked as paid')
            return

        try:
            mark_order_paid(order, 'paypal', json.dumps(payment.to_dict()))
        except Quota.QuotaExceededException as e:
            RequiredAction.objects.create(
                event=request.event, action_type='pretix.plugins.paypal.overpaid', data=json.dumps({
                    'order': order.code,
                    'payment': payment.id
                })
            )
            raise PaymentException(str(e))

        except SendMailException:
            messages.warning(request, _('There was an error sending the confirmation mail.'))
        return None

    def order_pending_render(self, request, order) -> str:
        retry = True
        try:
            if order.payment_info and json.loads(order.payment_info)['state'] == 'pending':
                retry = False
        except KeyError:
            pass
        template = get_template('pretixplugins/paypal/pending.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'retry': retry, 'order': order}
        return template.render(ctx)

    def order_control_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
        else:
            payment_info = None
        template = get_template('pretixplugins/paypal/control.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'payment_info': payment_info, 'order': order}
        return template.render(ctx)

    def _refund_form(self, request):
        return RefundForm(data=request.POST if request.method == "POST" else None)

    def order_control_refund_render(self, order, request) -> str:
        template = get_template('pretixplugins/paypal/control_refund.html')
        ctx = {
            'request': request,
            'form': self._refund_form(request),
        }
        return template.render(ctx)

    def order_control_refund_perform(self, request, order) -> "bool|str":
        f = self._refund_form(request)
        if not f.is_valid():
            messages.error(request, _('Your input was invalid, please try again.'))
            return
        elif f.cleaned_data.get('auto_refund') == 'manual':
            order = mark_order_refunded(order, user=request.user)
            order.payment_manual = True
            order.save()
            return

        self.init_api()

        if order.payment_info:
            payment_info = json.loads(order.payment_info)
        else:
            payment_info = None

        if not payment_info:
            mark_order_refunded(order, user=request.user)
            messages.warning(request, _('We were unable to transfer the money back automatically. '
                                        'Please get in touch with the customer and transfer it back manually.'))
            return

        for res in payment_info['transactions'][0]['related_resources']:
            for k, v in res.items():
                if k == 'sale':
                    sale = paypalrestsdk.Sale.find(v['id'])
                    break

        refund = sale.refund({})
        if not refund.success():
            mark_order_refunded(order, user=request.user)
            messages.warning(request, _('We were unable to transfer the money back automatically. '
                                        'Please get in touch with the customer and transfer it back manually.'))
        else:
            sale = paypalrestsdk.Payment.find(payment_info['id'])
            order = mark_order_refunded(order, user=request.user)
            order.payment_info = json.dumps(sale.to_dict())
            order.save()

    def order_can_retry(self, order):
        return self._is_still_available(order=order)

    def order_prepare(self, request, order):
        self.init_api()
        payment = paypalrestsdk.Payment({
            'intent': 'sale',
            'payer': {
                "payment_method": "paypal",
            },
            "redirect_urls": {
                "return_url": build_absolute_uri(request.event, 'plugins:paypal:return'),
                "cancel_url": build_absolute_uri(request.event, 'plugins:paypal:abort'),
            },
            "transactions": [
                {
                    "item_list": {
                        "items": [
                            {
                                "name": __('Order {slug}-{code}').format(slug=self.event.slug.upper(), code=order.code),
                                "quantity": 1,
                                "price": str(order.total),
                                "currency": order.event.currency
                            }
                        ]
                    },
                    "amount": {
                        "currency": request.event.currency,
                        "total": str(order.total)
                    },
                    "description": __('Order {order} for {event}').format(
                        event=request.event.name,
                        order=order.code
                    )
                }
            ]
        })
        request.session['payment_paypal_order'] = order.pk
        return self._create_payment(request, payment)
