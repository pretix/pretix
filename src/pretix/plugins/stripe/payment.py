import hashlib
import json
import logging
from collections import OrderedDict

import stripe
from django import forms
from django.conf import settings
from django.contrib import messages
from django.template.loader import get_template
from django.utils.translation import ugettext, ugettext_lazy as _

from pretix.base.models import Event, Quota, RequiredAction
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.base.settings import SettingsSandbox
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.plugins.stripe.models import ReferencedStripeObject

logger = logging.getLogger('pretix.plugins.stripe')


class RefundForm(forms.Form):
    auto_refund = forms.ChoiceField(
        initial='auto',
        label=_('Refund automatically?'),
        choices=(
            ('auto', _('Automatically refund charge with Stripe')),
            ('manual', _('Do not send refund instruction to Stripe, only mark as refunded in pretix'))
        ),
        widget=forms.RadioSelect,
    )


class StripeKeyValidator():
    def __init__(self, prefix):
        assert isinstance(prefix, str)
        assert len(prefix) > 0
        self._prefix = prefix

    def __call__(self, value):
        if not value.startswith(self._prefix):
            raise forms.ValidationError(
                _('The provided key "%(value)s" does not look valid. It should start with "%(prefix)s".'),
                code='invalid-stripe-secret-key',
                params={
                    'value': value,
                    'prefix': self._prefix,
                },
            )


class StripeSettingsHolder(BasePaymentProvider):
    identifier = 'stripe_settings'
    verbose_name = _('Stripe')
    is_enabled = False
    is_meta = True

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'stripe', event)

    def settings_content_render(self, request):
        return "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
            _('Please configure a <a href="https://dashboard.stripe.com/account/webhooks">Stripe Webhook</a> to '
              'the following endpoint in order to automatically cancel orders when charges are refunded externally '
              'and to process asynchronous payment methods like SOFORT.'),
            build_global_uri('plugins:stripe:webhook')
        )

    @property
    def settings_form_fields(self):
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('secret_key',
                 forms.CharField(
                     label=_('Secret key'),
                     help_text=_('<a target="_blank" rel="noopener" href="{docs_url}">{text}</a>').format(
                         text=_('Click here for a tutorial on how to obtain the required keys'),
                         docs_url='https://docs.pretix.eu/en/latest/user/payments/stripe.html'
                     ),
                     validators=(
                         StripeKeyValidator('sk_'),
                     ),
                 )),
                ('publishable_key',
                 forms.CharField(
                     label=_('Publishable key'),
                     validators=(
                         StripeKeyValidator('pk_'),
                     ),
                 )),
                ('ui',
                 forms.ChoiceField(
                     label=_('User interface'),
                     choices=(
                         ('pretix', _('Simple (pretix design)')),
                         ('checkout', _('Stripe Checkout')),
                     ),
                     help_text=_('Only relevant for credit card payments.')
                 )),
                ('method_cc',
                 forms.BooleanField(
                     label=_('Credit card payments'),
                     required=False,
                 )),
                ('method_giropay',
                 forms.BooleanField(
                     label=_('giropay'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_ideal',
                 forms.BooleanField(
                     label=_('iDEAL'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_alipay',
                 forms.BooleanField(
                     label=_('Alipay'),
                     disabled=self.event.currency not in ('EUR', 'AUD', 'CAD', 'GBP', 'HKD', 'JPY', 'NZD', 'SGD', 'USD'),
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_bancontact',
                 forms.BooleanField(
                     label=_('Bancontact'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first.'),
                     required=False,
                 )),
                ('method_sofort',
                 forms.BooleanField(
                     label=_('SOFORT'),
                     disabled=self.event.currency != 'EUR',
                     help_text=_('Needs to be enabled in your Stripe account first. Note that, despite the name, '
                                 'payments are not immediately confirmed but might take some time.'),
                     required=False,
                 )),
            ]
        )


class StripeMethod(BasePaymentProvider):
    identifier = ''
    method = ''

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'stripe', event)

    @property
    def settings_form_fields(self):
        return {}

    @property
    def is_enabled(self) -> bool:
        return self.settings.get('_enabled', as_type=bool) and self.settings.get('method_{}'.format(self.method),
                                                                                 as_type=bool)

    def order_prepare(self, request, order):
        return self.checkout_prepare(request, None)

    def _get_amount(self, order):
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
        return int(order.total * 10 ** places)

    def _init_api(self):
        stripe.api_version = '2017-06-05'
        stripe.api_key = self.settings.get('secret_key')

    def checkout_confirm_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings, 'provider': self}
        return template.render(ctx)

    def order_can_retry(self, order):
        return self._is_still_available(order=order)

    def _charge_source(self, request, source, order):
        try:
            charge = stripe.Charge.create(
                amount=self._get_amount(order),
                currency=self.event.currency.lower(),
                source=source,
                metadata={
                    'order': str(order.id),
                    'event': self.event.id,
                    'code': order.code
                },
                # TODO: Is this sufficient?
                idempotency_key=str(self.event.id) + order.code + source
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
            order.save(update_fields=['payment_info'])
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
            order.save(update_fields=['payment_info'])
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))
        else:
            ReferencedStripeObject.objects.get_or_create(order=order, reference=charge.id)
            if charge.status == 'succeeded' and charge.paid:
                try:
                    mark_order_paid(order, self.identifier, str(charge))
                except Quota.QuotaExceededException as e:
                    RequiredAction.objects.create(
                        event=self.event, action_type='pretix.plugins.stripe.overpaid', data=json.dumps({
                            'order': order.code,
                            'charge': charge.id
                        })
                    )
                    raise PaymentException(str(e))

                except SendMailException:
                    raise PaymentException(_('There was an error sending the confirmation mail.'))
            elif charge.status == 'pending':
                if request:
                    messages.warning(request, _('Your payment is pending completion. We will inform you as soon as the '
                                                'payment completed.'))
                order.payment_info = str(charge)
                order.save(update_fields=['payment_info'])
                return
            else:
                logger.info('Charge failed: %s' % str(charge))
                order.payment_info = str(charge)
                order.save(update_fields=['payment_info'])
                raise PaymentException(_('Stripe reported an error: %s') % charge.failure_message)

    def order_pending_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
        else:
            payment_info = None
        template = get_template('pretixplugins/stripe/pending.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'provider': self,
            'order': order,
            'payment_info': payment_info,
        }
        return template.render(ctx)

    def order_control_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
            if 'amount' in payment_info:
                payment_info['amount'] /= 10 ** settings.CURRENCY_PLACES.get(self.event.currency, 2)
        else:
            payment_info = None
        template = get_template('pretixplugins/stripe/control.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'payment_info': payment_info,
            'order': order,
            'method': self.method,
            'provider': self,
        }
        return template.render(ctx)

    def _refund_form(self, request):
        return RefundForm(data=request.POST if request.method == "POST" else None)

    def order_control_refund_render(self, order, request) -> str:
        template = get_template('pretixplugins/stripe/control_refund.html')
        ctx = {
            'request': request,
            'form': self._refund_form(request),
        }
        return template.render(ctx)

    def order_control_refund_perform(self, request, order) -> "bool|str":
        self._init_api()

        f = self._refund_form(request)
        if not f.is_valid():
            messages.error(request, _('Your input was invalid, please try again.'))
            return
        elif f.cleaned_data.get('auto_refund') == 'manual':
            order = mark_order_refunded(order, user=request.user)
            order.payment_manual = True
            order.save()
            return

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

    def payment_perform(self, request, order) -> str:
        self._init_api()
        try:
            source = self._create_source(request, order)
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
            order.save(update_fields=['payment_info'])
            raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                     'with us if this problem persists.'))

        ReferencedStripeObject.objects.get_or_create(order=order, reference=source.id)
        order.payment_info = str(source)
        order.save(update_fields=['payment_info'])
        request.session['payment_stripe_order_secret'] = order.secret
        return source.redirect.url


class StripeCC(StripeMethod):
    identifier = 'stripe'
    verbose_name = _('Credit card via Stripe')
    public_name = _('Credit card')
    method = 'cc'

    def payment_form_render(self, request) -> str:
        ui = self.settings.get('ui', default='pretix')
        if ui == 'checkout':
            template = get_template('pretixplugins/stripe/checkout_payment_form_stripe_checkout.html')
        else:
            template = get_template('pretixplugins/stripe/checkout_payment_form.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
        }
        return template.render(ctx)

    def payment_is_valid_session(self, request):
        return request.session.get('payment_stripe_token', '') != ''

    def checkout_prepare(self, request, cart):
        token = request.POST.get('stripe_token', '')
        request.session['payment_stripe_token'] = token
        request.session['payment_stripe_brand'] = request.POST.get('stripe_card_brand', '')
        request.session['payment_stripe_last4'] = request.POST.get('stripe_card_last4', '')
        if token == '':
            messages.error(request, _('You may need to enable JavaScript for Stripe payments.'))
            return False
        return True

    def payment_perform(self, request, order) -> str:
        self._init_api()

        if request.session['payment_stripe_token'].startswith('src_'):
            try:
                src = stripe.Source.retrieve(request.session['payment_stripe_token'])
                if src.type == 'card' and src.card and src.card.three_d_secure == 'required':
                    request.session['payment_stripe_order_secret'] = order.secret
                    source = stripe.Source.create(
                        type='three_d_secure',
                        amount=self._get_amount(order),
                        currency=self.event.currency.lower(),
                        three_d_secure={
                            'card': src.id
                        },
                        metadata={
                            'order': str(order.id),
                            'event': self.event.id,
                            'code': order.code
                        },
                        redirect={
                            'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                                'order': order.code,
                                'hash': hashlib.sha1(order.secret.lower().encode()).hexdigest(),
                            })
                        },
                    )
                    if source.status == "pending":
                        order.payment_info = str(source)
                        order.save(update_fields=['payment_info'])
                        return source.redirect.url
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
                order.save(update_fields=['payment_info'])
                raise PaymentException(_('We had trouble communicating with Stripe. Please try again and get in touch '
                                         'with us if this problem persists.'))

        try:
            self._charge_source(request, request.session['payment_stripe_token'], order)
        finally:
            del request.session['payment_stripe_token']


class StripeGiropay(StripeMethod):
    identifier = 'stripe_giropay'
    verbose_name = _('giropay via Stripe')
    public_name = _('giropay')
    method = 'giropay'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_giropay.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('account', forms.CharField(label=_('Account holder'))),
        ])

    def _create_source(self, request, order):
        try:
            source = stripe.Source.create(
                type='giropay',
                amount=self._get_amount(order),
                currency=self.event.currency.lower(),
                metadata={
                    'order': str(order.id),
                    'event': self.event.id,
                    'code': order.code
                },
                owner={
                    'name': request.session.get('payment_stripe_giropay_account') or ugettext('unknown name')
                },
                giropay={
                    'statement_descriptor': ugettext('{event}-{code}').format(
                        event=self.event.slug.upper(),
                        code=order.code
                    )[:35]
                },
                redirect={
                    'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                        'order': order.code,
                        'hash': hashlib.sha1(order.secret.lower().encode()).hexdigest(),
                    })
                },
            )
            return source
        finally:
            if 'payment_stripe_giropay_account' in request.session:
                del request.session['payment_stripe_giropay_account']

    def payment_is_valid_session(self, request):
        return (
            request.session.get('payment_stripe_giropay_account', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session['payment_stripe_giropay_account'] = form.cleaned_data['account']
            return True
        return False


class StripeIdeal(StripeMethod):
    identifier = 'stripe_ideal'
    verbose_name = _('iDEAL via Stripe')
    public_name = _('iDEAL')
    method = 'ideal'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
        }
        return template.render(ctx)

    def _create_source(self, request, order):
        source = stripe.Source.create(
            type='ideal',
            amount=self._get_amount(order),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(order.id),
                'event': self.event.id,
                'code': order.code
            },
            ideal={
                'statement_descriptor': ugettext('{event}-{code}').format(
                    event=self.event.slug.upper(),
                    code=order.code
                )
            },
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': order.code,
                    'hash': hashlib.sha1(order.secret.lower().encode()).hexdigest(),
                })
            },
        )
        return source

    def payment_is_valid_session(self, request):
        return True

    def checkout_prepare(self, request, cart):
        return True


class StripeAlipay(StripeMethod):
    identifier = 'stripe_alipay'
    verbose_name = _('Alipay via Stripe')
    public_name = _('Alipay')
    method = 'alipay'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_simple.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
        }
        return template.render(ctx)

    def _create_source(self, request, order):
        source = stripe.Source.create(
            type='alipay',
            amount=self._get_amount(order),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(order.id),
                'event': self.event.id,
                'code': order.code
            },
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': order.code,
                    'hash': hashlib.sha1(order.secret.lower().encode()).hexdigest(),
                })
            },
        )
        return source

    def payment_is_valid_session(self, request):
        return True

    def checkout_prepare(self, request, cart):
        return True


class StripeBancontact(StripeMethod):
    identifier = 'stripe_bancontact'
    verbose_name = _('Bancontact via Stripe')
    public_name = _('Bancontact')
    method = 'bancontact'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_bancontact.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('account', forms.CharField(label=_('Account holder'), min_length=3)),
        ])

    def _create_source(self, request, order):
        try:
            source = stripe.Source.create(
                type='bancontact',
                amount=self._get_amount(order),
                currency=self.event.currency.lower(),
                metadata={
                    'order': str(order.id),
                    'event': self.event.id,
                    'code': order.code
                },
                owner={
                    'name': request.session.get('payment_stripe_bancontact_account') or ugettext('unknown name')
                },
                bancontact={
                    'statement_descriptor': ugettext('{event}-{code}').format(
                        event=self.event.slug.upper(),
                        code=order.code
                    )[:35]
                },
                redirect={
                    'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                        'order': order.code,
                        'hash': hashlib.sha1(order.secret.lower().encode()).hexdigest(),
                    })
                },
            )
            return source
        finally:
            if 'payment_stripe_bancontact_account' in request.session:
                del request.session['payment_stripe_bancontact_account']

    def payment_is_valid_session(self, request):
        return (
            request.session.get('payment_stripe_bancontact_account', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session['payment_stripe_bancontact_account'] = form.cleaned_data['account']
            return True
        return False


class StripeSofort(StripeMethod):
    identifier = 'stripe_sofort'
    verbose_name = _('SOFORT via Stripe')
    public_name = _('SOFORT')
    method = 'sofort'

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_form_sofort.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'form': self.payment_form(request)
        }
        return template.render(ctx)

    @property
    def payment_form_fields(self):
        return OrderedDict([
            ('bank_country', forms.ChoiceField(label=_('Country of your bank'), choices=(
                ('de', _('Germany')),
                ('at', _('Austria')),
                ('be', _('Belgium')),
                ('nl', _('Netherlands')),
                ('es', _('Spain'))
            ))),
        ])

    def _create_source(self, request, order):
        source = stripe.Source.create(
            type='sofort',
            amount=self._get_amount(order),
            currency=self.event.currency.lower(),
            metadata={
                'order': str(order.id),
                'event': self.event.id,
                'code': order.code
            },
            sofort={
                'country': request.session.get('payment_stripe_sofort_bank_country'),
                'statement_descriptor': ugettext('{event}-{code}').format(
                    event=self.event.slug.upper(),
                    code=order.code
                )[:35]
            },
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': order.code,
                    'hash': hashlib.sha1(order.secret.lower().encode()).hexdigest(),
                })
            },
        )
        return source

    def payment_is_valid_session(self, request):
        return (
            request.session.get('payment_stripe_sofort_bank_country', '') != ''
        )

    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if form.is_valid():
            request.session['payment_stripe_sofort_bank_country'] = form.cleaned_data['bank_country']
            return True
        return False

    def order_can_retry(self, order):
        try:
            if order.payment_info:
                d = json.loads(order.payment_info)
                if d.get('object') == 'charge' and d.get('status') == 'pending':
                    return False
        except ValueError:
            pass
        return self._is_still_available(order=order)
