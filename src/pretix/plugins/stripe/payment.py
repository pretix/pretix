import hashlib
import json
import logging
import urllib.parse
from collections import OrderedDict

import stripe
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.template.loader import get_template
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.http import urlquote
from django.utils.translation import pgettext, ugettext, ugettext_lazy as _

from pretix import __version__
from pretix.base.models import Event, Order, Quota, RequiredAction
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import mark_order_paid, mark_order_refunded
from pretix.base.settings import SettingsSandbox
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.plugins.stripe.forms import StripeKeyValidator
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


class StripeSettingsHolder(BasePaymentProvider):
    identifier = 'stripe_settings'
    verbose_name = _('Stripe')
    is_enabled = False
    is_meta = True

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'stripe', event)

    def get_connect_url(self, request):
        request.session['payment_stripe_oauth_event'] = request.event.pk
        if 'payment_stripe_oauth_token' not in request.session:
            request.session['payment_stripe_oauth_token'] = get_random_string(32)
        return (
            "https://connect.stripe.com/oauth/authorize?response_type=code&client_id={}&state={}"
            "&scope=read_write&redirect_uri={}"
        ).format(
            self.settings.connect_client_id,
            request.session['payment_stripe_oauth_token'],
            urlquote(build_global_uri('plugins:stripe:oauth.return')),
        )

    def settings_content_render(self, request):
        if self.settings.connect_client_id and not self.settings.secret_key:
            # Use Stripe connect
            if not self.settings.connect_user_id:
                return (
                    "<p>{}</p>"
                    "<a href='{}' class='btn btn-primary btn-lg'>{}</a>"
                ).format(
                    _('To accept payments via Stripe, you will need an account at Stripe. By clicking on the '
                      'following button, you can either create a new Stripe account connect pretix to an existing '
                      'one.'),
                    self.get_connect_url(request),
                    _('Connect with Stripe')
                )
            else:
                return (
                    "<button formaction='{}' class='btn btn-danger'>{}</button>"
                ).format(
                    reverse('plugins:stripe:oauth.disconnect', kwargs={
                        'organizer': self.event.organizer.slug,
                        'event': self.event.slug,
                    }),
                    _('Disconnect from Stripe')
                )
        else:
            return "<div class='alert alert-info'>%s<br /><code>%s</code></div>" % (
                _('Please configure a <a href="https://dashboard.stripe.com/account/webhooks">Stripe Webhook</a> to '
                  'the following endpoint in order to automatically cancel orders when charges are refunded externally '
                  'and to process asynchronous payment methods like SOFORT.'),
                build_global_uri('plugins:stripe:webhook')
            )

    @property
    def settings_form_fields(self):
        if self.settings.connect_client_id and not self.settings.secret_key:
            # Stripe connect
            if self.settings.connect_user_id:
                fields = [
                    ('connect_user_name',
                     forms.CharField(
                         label=_('Stripe account'),
                         disabled=True
                     )),
                    ('endpoint',
                     forms.ChoiceField(
                         label=_('Endpoint'),
                         initial='live',
                         choices=(
                             ('live', pgettext('stripe', 'Live')),
                             ('test', pgettext('stripe', 'Testing')),
                         ),
                     )),
                ]
            else:
                return {}
        else:
            fields = [
                ('publishable_key',
                 forms.CharField(
                     label=_('Publishable key'),
                     help_text=_('<a target="_blank" rel="noopener" href="{docs_url}">{text}</a>').format(
                         text=_('Click here for a tutorial on how to obtain the required keys'),
                         docs_url='https://docs.pretix.eu/en/latest/user/payments/stripe.html'
                     ),
                     validators=(
                         StripeKeyValidator('pk_'),
                     ),
                 )),
                ('secret_key',
                 forms.CharField(
                     label=_('Secret key'),
                     validators=(
                         StripeKeyValidator(['sk_', 'rk_']),
                     ),
                 )),
            ]
        d = OrderedDict(
            fields + [
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
                     help_text=(
                         _('Needs to be enabled in your Stripe account first.') +
                         '<div class="alert alert-warning">%s</div>' % _(
                             'Despite the name, Sofort payments via Stripe are <strong>not</strong> processed '
                             'instantly but might take up to <strong>14 days</strong> to be confirmed in some cases. '
                             'Please only activate this payment method if your payment term allows for this lag.'
                         )
                     ),
                     required=False,
                 )),
                ('cc_3ds_mode',
                 forms.ChoiceField(
                     label=_('3D Secure mode'),
                     help_text=_('This determines when we will use the 3D Secure methods for credit card payments. '
                                 'Using 3D Secure (also known as Verified by VISA or MasterCard SecureCode) reduces '
                                 'the risk of fraud but makes the payment process a bit longer.'),
                     choices=(
                         ('required', pgettext('stripe 3dsecure', 'Only when required by the card')),
                         ('recommended', pgettext('stripe 3dsecure', 'Always when recommended by Stripe')),
                         ('optional', pgettext('stripe 3dsecure', 'Always when supported by the card')),
                     ),
                 )),
            ] + list(super().settings_form_fields.items())
        )
        d.move_to_end('_enabled', last=False)
        return d


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

    @property
    def api_kwargs(self):
        if self.settings.connect_client_id and self.settings.connect_user_id:
            if self.settings.get('endpoint', 'live') == 'live':
                kwargs = {
                    'api_key': self.settings.connect_secret_key,
                    'stripe_account': self.settings.connect_user_id
                }
            else:
                kwargs = {
                    'api_key': self.settings.connect_test_secret_key,
                    'stripe_account': self.settings.connect_user_id
                }
        else:
            kwargs = {
                'api_key': self.settings.secret_key,
            }
        return kwargs

    def _init_api(self):
        stripe.api_version = '2018-02-28'
        stripe.set_app_info("pretix", version=__version__, url="https://pretix.eu")

    def checkout_confirm_render(self, request) -> str:
        template = get_template('pretixplugins/stripe/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings, 'provider': self}
        return template.render(ctx)

    def order_can_retry(self, order):
        return self._is_still_available(order=order)

    def _charge_source(self, request, source, order):
        try:
            params = {}
            if not source.startswith('src_'):
                params['statement_descriptor'] = ugettext('{event}-{code}').format(
                    event=self.event.slug.upper(),
                    code=order.code
                )[:22]
            params.update(self.api_kwargs)
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
                idempotency_key=str(self.event.id) + order.code + source,
                **params
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
            ch = stripe.Charge.retrieve(payment_info['id'], **self.api_kwargs)
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
        return self.redirect(request, source.redirect.url)

    def redirect(self, request, url):
        if request.session.get('iframe_session', False):
            signer = signing.Signer(salt='safe-redirect')
            return (
                build_absolute_uri(request.event, 'plugins:stripe:redirect') + '?url=' +
                urllib.parse.quote(signer.sign(url))
            )
        else:
            return str(url)

    def shred_payment_info(self, order: Order):
        if not order.payment_info:
            return
        d = json.loads(order.payment_info)
        new = {}
        if 'source' in d:
            new['source'] = {
                'id': d['source'].get('id'),
                'type': d['source'].get('type'),
                'brand': d['source'].get('brand'),
                'last4': d['source'].get('last4'),
                'bank_name': d['source'].get('bank_name'),
                'bank': d['source'].get('bank'),
                'bic': d['source'].get('bic'),
                'card': {
                    'brand': d['source'].get('card', {}).get('brand'),
                    'country': d['source'].get('card', {}).get('cuntry'),
                    'last4': d['source'].get('card', {}).get('last4'),
                }
            }
            new['amount'] = d['amount']
            new['currency'] = d['currency']
            new['status'] = d['status']
            new['id'] = d['id']
            new['_shredded'] = True
        order.payment_info = json.dumps(new)
        order.save(update_fields=['payment_info'])


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

    def _use_3ds(self, card):
        if self.settings.cc_3ds_mode == 'recommended':
            return card.three_d_secure in ('required', 'recommended')
        elif self.settings.cc_3ds_mode == 'optional':
            return card.three_d_secure in ('required', 'recommended', 'optional')
        else:
            return card.three_d_secure == 'required'

    def payment_perform(self, request, order) -> str:
        self._init_api()

        if request.session['payment_stripe_token'].startswith('src_'):
            try:
                src = stripe.Source.retrieve(request.session['payment_stripe_token'], **self.api_kwargs)
                if src.type == 'card' and src.card and self._use_3ds(src.card):
                    request.session['payment_stripe_order_secret'] = order.secret
                    source = stripe.Source.create(
                        type='three_d_secure',
                        amount=self._get_amount(order),
                        currency=self.event.currency.lower(),
                        three_d_secure={
                            'card': src.id
                        },
                        statement_descriptor=ugettext('{event}-{code}').format(
                            event=self.event.slug.upper(),
                            code=order.code
                        )[:22],
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
                        **self.api_kwargs
                    )
                    if source.status == "pending":
                        order.payment_info = str(source)
                        order.save(update_fields=['payment_info'])
                        return self.redirect(request, source.redirect.url)
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
                **self.api_kwargs
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
                )[:22]
            },
            redirect={
                'return_url': build_absolute_uri(self.event, 'plugins:stripe:return', kwargs={
                    'order': order.code,
                    'hash': hashlib.sha1(order.secret.lower().encode()).hexdigest(),
                })
            },
            **self.api_kwargs
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
            **self.api_kwargs
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
                **self.api_kwargs
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
            **self.api_kwargs
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
