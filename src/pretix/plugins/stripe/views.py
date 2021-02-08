import hashlib
import json
import logging

import stripe
from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import FormView
from django_scopes import scopes_disabled

from pretix.base.models import Event, Order, OrderPayment, Organizer, Quota
from pretix.base.payment import PaymentException
from pretix.base.services.locking import LockTimeoutException
from pretix.base.settings import GlobalSettingsObject
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, event_permission_required,
)
from pretix.control.views.event import DecoupleMixin
from pretix.control.views.organizer import OrganizerDetailViewMixin
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.stripe.forms import OrganizerStripeSettingsForm
from pretix.plugins.stripe.models import ReferencedStripeObject
from pretix.plugins.stripe.payment import StripeCC, StripeSettingsHolder
from pretix.plugins.stripe.tasks import (
    get_domain_for_event, stripe_verify_domain,
)

logger = logging.getLogger('pretix.plugins.stripe')


@xframe_options_exempt
def redirect_view(request, *args, **kwargs):
    signer = signing.Signer(salt='safe-redirect')
    try:
        url = signer.unsign(request.GET.get('url', ''))
    except signing.BadSignature:
        return HttpResponseBadRequest('Invalid parameter')

    r = render(request, 'pretixplugins/stripe/redirect.html', {
        'url': url,
    })
    r._csp_ignore = True
    return r


@scopes_disabled()
def oauth_return(request, *args, **kwargs):
    if 'payment_stripe_oauth_event' not in request.session or 'payment_stripe_oauth_account' not in request.session:
        messages.error(request, _('An error occurred during connecting with Stripe, please try again.'))
        return redirect(reverse('control:index'))

    event = get_object_or_404(Event, pk=request.session['payment_stripe_oauth_event'])

    gs = GlobalSettingsObject()
    stripe.api_key = gs.settings.payment_stripe_connect_secret_key or gs.settings.payment_stripe_connect_test_secret_key

    try:
        account = stripe.Account.retrieve(request.session['payment_stripe_oauth_account'])
    except:
        logger.exception('Failed to obtain OAuth token')
        messages.error(request, _('An error occurred during connecting with Stripe, please try again.'))
    else:
        event.settings.payment_stripe_connect_user_id = account.id
        event.settings.payment_stripe_connect_user_name = (
            account.get('business_profile', {}).get('name') or account.get('email')
        )
        if request.session.get('payment_stripe_oauth_enable', False):
            event.settings.payment_stripe__enabled = True
            del request.session['payment_stripe_oauth_enable']

        stripe_verify_domain.apply_async(args=(event.pk, get_domain_for_event(event)))

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': event.organizer.slug,
        'event': event.slug,
        'provider': 'stripe_settings'
    }))


@csrf_exempt
@require_POST
@scopes_disabled()
def webhook(request, *args, **kwargs):
    event_json = json.loads(request.body.decode('utf-8'))

    # We do not check for the event type as we are not interested in the event it self,
    # we just use it as a trigger to look the charge up to be absolutely sure.
    # Another reason for this is that stripe events are not authenticated, so they could
    # come from anywhere.

    if event_json['data']['object']['object'] == "charge":
        func = charge_webhook
        objid = event_json['data']['object']['id']
    elif event_json['data']['object']['object'] == "dispute":
        func = charge_webhook
        objid = event_json['data']['object']['charge']
    elif event_json['data']['object']['object'] == "source":
        func = source_webhook
        objid = event_json['data']['object']['id']
    elif event_json['data']['object']['object'] == "payment_intent":
        func = paymentintent_webhook
        objid = event_json['data']['object']['id']
    else:
        return HttpResponse("Not interested in this data type", status=200)

    try:
        rso = ReferencedStripeObject.objects.select_related('order', 'order__event').get(reference=objid)
        return func(rso.order.event, event_json, objid, rso)
    except ReferencedStripeObject.DoesNotExist:
        if event_json['data']['object']['object'] == "charge" and 'payment_intent' in event_json['data']['object']:
            # If we receive a charge webhook *before* the payment intent webhook, we don't know the charge ID yet
            # and can't match it -- but we know the payment intent ID!
            try:
                rso = ReferencedStripeObject.objects.select_related('order', 'order__event').get(
                    reference=event_json['data']['object']['payment_intent']
                )
                return func(rso.order.event, event_json, objid, rso)
            except ReferencedStripeObject.DoesNotExist:
                return HttpResponse("Unable to detect event", status=200)
        elif hasattr(request, 'event') and func != paymentintent_webhook:
            # This is a legacy integration from back when didn't have ReferencedStripeObject. This can't happen for
            # payment intents or charges connected with payment intents since they didn't exist back then. Our best
            # hope is to go for request.event and see if we can find the order ID.
            return func(request.event, event_json, objid, None)
        else:
            # Okay, this is probably not an event that concerns us, maybe other applications talk to the same stripe
            # account
            return HttpResponse("Unable to detect event", status=200)


SOURCE_TYPES = {
    'sofort': 'stripe_sofort',
    'three_d_secure': 'stripe',
    'card': 'stripe',
    'giropay': 'stripe_giropay',
    'ideal': 'stripe_ideal',
    'alipay': 'stripe_alipay',
    'bancontact': 'stripe_bancontact',
}


def charge_webhook(event, event_json, charge_id, rso):
    prov = StripeCC(event)
    prov._init_api()

    try:
        charge = stripe.Charge.retrieve(charge_id, expand=['dispute'], **prov.api_kwargs)
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Charge not found', status=500)

    metadata = charge['metadata']
    if 'event' not in metadata:
        return HttpResponse('Event not given in charge metadata', status=200)

    if int(metadata['event']) != event.pk:
        return HttpResponse('Not interested in this event', status=200)

    if rso and rso.payment:
        order = rso.payment.order
        payment = rso.payment
    elif rso:
        order = rso.order
        payment = None
    else:
        try:
            order = event.orders.get(id=metadata['order'])
        except Order.DoesNotExist:
            return HttpResponse('Order not found', status=200)
        payment = None

    with transaction.atomic():
        if not payment:
            payment = order.payments.filter(
                info__icontains=charge['id'],
                provider__startswith='stripe',
                amount=prov._amount_to_decimal(charge['amount']),
            ).select_for_update().last()
        if not payment:
            payment = order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider=SOURCE_TYPES.get(charge['source'].get('type', charge['source'].get('object', 'card')), 'stripe'),
                amount=prov._amount_to_decimal(charge['amount']),
                info=str(charge),
            )

        if payment.provider != prov.identifier:
            prov = payment.payment_provider
            prov._init_api()

        order.log_action('pretix.plugins.stripe.event', data=event_json)

        is_refund = charge['refunds']['total_count'] or charge['dispute']
        if is_refund:
            known_refunds = [r.info_data.get('id') for r in payment.refunds.all()]
            migrated_refund_amounts = [r.amount for r in payment.refunds.all() if not r.info_data.get('id')]
            for r in charge['refunds']['data']:
                a = prov._amount_to_decimal(r['amount'])
                if r['status'] in ('failed', 'canceled'):
                    continue

                if a in migrated_refund_amounts:
                    migrated_refund_amounts.remove(a)
                    continue

                if r['id'] not in known_refunds:
                    payment.create_external_refund(
                        amount=a,
                        info=str(r)
                    )
            if charge['dispute']:
                if charge['dispute']['status'] != 'won' and charge['dispute']['id'] not in known_refunds:
                    a = prov._amount_to_decimal(charge['dispute']['amount'])
                    if a in migrated_refund_amounts:
                        migrated_refund_amounts.remove(a)
                    else:
                        payment.create_external_refund(
                            amount=a,
                            info=str(charge['dispute'])
                        )
        elif charge['status'] == 'succeeded' and payment.state in (OrderPayment.PAYMENT_STATE_PENDING,
                                                                   OrderPayment.PAYMENT_STATE_CREATED,
                                                                   OrderPayment.PAYMENT_STATE_CANCELED,
                                                                   OrderPayment.PAYMENT_STATE_FAILED):
            try:
                payment.confirm()
            except LockTimeoutException:
                return HttpResponse("Lock timeout, please try again.", status=503)
            except Quota.QuotaExceededException:
                pass
        elif charge['status'] == 'failed' and payment.state in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED):
            payment.fail(info=str(charge))

    return HttpResponse(status=200)


def source_webhook(event, event_json, source_id, rso):
    prov = StripeCC(event)
    prov._init_api()
    try:
        src = stripe.Source.retrieve(source_id, **prov.api_kwargs)
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Charge not found', status=500)

    metadata = src['metadata']
    if 'event' not in metadata:
        return HttpResponse('Event not given in charge metadata', status=200)

    if int(metadata['event']) != event.pk:
        return HttpResponse('Not interested in this event', status=200)

    with transaction.atomic():
        if rso and rso.payment:
            order = rso.payment.order
            payment = rso.payment
        elif rso:
            order = rso.order
            payment = None
        else:
            try:
                order = event.orders.get(id=metadata['order'])
            except Order.DoesNotExist:
                return HttpResponse('Order not found', status=200)
            payment = None

        if not payment:
            payment = order.payments.filter(
                info__icontains=src['id'],
                provider__startswith='stripe',
                amount=prov._amount_to_decimal(src['amount']) if src['amount'] is not None else order.total,
            ).last()
        if not payment:
            payment = order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider=SOURCE_TYPES.get(src['type'], 'stripe'),
                amount=prov._amount_to_decimal(src['amount']) if src['amount'] is not None else order.total,
                info=str(src),
            )

        if payment.provider != prov.identifier:
            prov = payment.payment_provider
            prov._init_api()

        order.log_action('pretix.plugins.stripe.event', data=event_json)
        go = (event_json['type'] == 'source.chargeable' and
              payment.state in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED) and
              src.status == 'chargeable')
        if go:
            try:
                prov._charge_source(None, source_id, payment)
            except PaymentException:
                logger.exception('Webhook error')

        elif src.status == 'failed':
            payment.fail(info=str(src))
        elif src.status == 'canceled' and payment.state in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED):
            payment.info = str(src)
            payment.state = OrderPayment.PAYMENT_STATE_CANCELED
            payment.save()

    return HttpResponse(status=200)


def paymentintent_webhook(event, event_json, paymentintent_id, rso):
    prov = StripeCC(event)
    prov._init_api()

    try:
        paymentintent = stripe.PaymentIntent.retrieve(paymentintent_id, **prov.api_kwargs)
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Charge not found', status=500)

    for charge in paymentintent.charges.data:
        ReferencedStripeObject.objects.get_or_create(
            reference=charge.id,
            defaults={'order': rso.payment.order, 'payment': rso.payment}
        )

    return HttpResponse(status=200)


@event_permission_required('can_change_event_settings')
@require_POST
def oauth_disconnect(request, **kwargs):
    del request.event.settings.payment_stripe_publishable_key
    del request.event.settings.payment_stripe_publishable_test_key
    del request.event.settings.payment_stripe_connect_access_token
    del request.event.settings.payment_stripe_connect_refresh_token
    del request.event.settings.payment_stripe_connect_user_id
    del request.event.settings.payment_stripe_connect_user_name
    request.event.settings.payment_stripe__enabled = False
    messages.success(request, _('Your Stripe account has been disconnected.'))

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
        'provider': 'stripe_settings'
    }))


@event_permission_required('can_change_event_settings')
def oauth_connect(request, **kwargs):
    gs = GlobalSettingsObject()
    stripe.api_key = gs.settings.payment_stripe_connect_secret_key or gs.settings.payment_stripe_connect_test_secret_key

    request.session['payment_stripe_oauth_event'] = request.event.pk
    try:
        account = stripe.Account.create(
            type='standard',
            metadata={
                'organizer': request.organizer.slug,
            }
        )
        request.session['payment_stripe_oauth_account'] = account.stripe_id
        account_link = stripe.AccountLink.create(
            account=account.stripe_id,
            return_url=build_global_uri('plugins:stripe:oauth.return'),
            refresh_url=build_global_uri('plugins:stripe:oauth.connect', kwargs={
                'organizer': request.organizer.slug,
                'event': request.event.slug,
            }),
            type='account_onboarding',
        )
    except:
        logger.exception('Failed to obtain account link')
        messages.error(request, _('An error occurred during connecting with Stripe, please try again.'))
        return redirect(reverse('control:event.settings.payment.provider', kwargs={
            'organizer': request.event.organizer.slug,
            'event': request.event.slug,
            'provider': 'stripe_settings'
        }))

    return redirect(account_link.url)


@xframe_options_exempt
def applepay_association(request, *args, **kwargs):
    r = render(request, 'pretixplugins/stripe/apple-developer-merchantid-domain-association')
    r._csp_ignore = True
    return r


class StripeOrderView:
    def dispatch(self, request, *args, **kwargs):
        try:
            self.order = request.event.orders.get(code=kwargs['order'])
            if hashlib.sha1(self.order.secret.lower().encode()).hexdigest() != kwargs['hash'].lower():
                raise Http404('')
        except Order.DoesNotExist:
            # Do a hash comparison as well to harden timing attacks
            if 'abcdefghijklmnopq'.lower() == hashlib.sha1('abcdefghijklmnopq'.encode()).hexdigest():
                raise Http404('')
            else:
                raise Http404('')
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def payment(self):
        return get_object_or_404(self.order.payments,
                                 pk=self.kwargs['payment'],
                                 provider__startswith='stripe')

    @cached_property
    def pprov(self):
        return self.request.event.get_payment_providers()[self.payment.provider]

    def _redirect_to_order(self):
        if self.request.session.get('payment_stripe_order_secret') != self.order.secret and self.payment.provider != 'stripe_ideal':
            messages.error(self.request, _('Sorry, there was an error in the payment process. Please check the link '
                                           'in your emails to continue.'))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        return redirect(eventreverse(self.request.event, 'presale:event.order', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        }) + ('?paid=yes' if self.order.status == Order.STATUS_PAID else ''))


@method_decorator(xframe_options_exempt, 'dispatch')
class ReturnView(StripeOrderView, View):
    def get(self, request, *args, **kwargs):
        prov = self.pprov
        prov._init_api()
        try:
            src = stripe.Source.retrieve(request.GET.get('source'), **prov.api_kwargs)
        except stripe.error.InvalidRequestError:
            logger.exception('Could not retrieve source')
            messages.error(self.request, _('Sorry, there was an error in the payment process. Please check the link '
                                           'in your emails to continue.'))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        if src.client_secret != request.GET.get('client_secret'):
            messages.error(self.request, _('Sorry, there was an error in the payment process. Please check the link '
                                           'in your emails to continue.'))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        with transaction.atomic():
            self.order.refresh_from_db()
            self.payment.refresh_from_db()
            if self.payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
                if 'payment_stripe_token' in request.session:
                    del request.session['payment_stripe_token']
                return self._redirect_to_order()

            if src.status == 'chargeable':
                try:
                    prov._charge_source(request, src.id, self.payment)
                except PaymentException as e:
                    messages.error(request, str(e))
                    return self._redirect_to_order()
                finally:
                    if 'payment_stripe_token' in request.session:
                        del request.session['payment_stripe_token']
            elif src.status == 'consumed':
                # Webhook was faster, wow! ;)
                if 'payment_stripe_token' in request.session:
                    del request.session['payment_stripe_token']
                return self._redirect_to_order()
            elif src.status == 'pending':
                self.payment.state = OrderPayment.PAYMENT_STATE_PENDING
                self.payment.info = str(src)
                self.payment.save()
            else:  # failed or canceled
                self.payment.fail(info=str(src))
                messages.error(self.request, _('We had trouble authorizing your card payment. Please try again and '
                                               'get in touch with us if this problem persists.'))
        return self._redirect_to_order()


@method_decorator(xframe_options_exempt, 'dispatch')
class ScaView(StripeOrderView, View):

    def get(self, request, *args, **kwargs):
        prov = self.pprov
        prov._init_api()

        if self.payment.state in (OrderPayment.PAYMENT_STATE_CONFIRMED,
                                  OrderPayment.PAYMENT_STATE_CANCELED,
                                  OrderPayment.PAYMENT_STATE_FAILED):
            return self._redirect_to_order()

        payment_info = json.loads(self.payment.info)

        if 'id' in payment_info:
            try:
                intent = stripe.PaymentIntent.retrieve(
                    payment_info['id'],
                    **prov.api_kwargs
                )
            except stripe.error.InvalidRequestError:
                logger.exception('Could not retrieve payment intent')
                messages.error(self.request, _('Sorry, there was an error in the payment process.'))
                return self._redirect_to_order()
        else:
            messages.error(self.request, _('Sorry, there was an error in the payment process.'))
            return self._redirect_to_order()

        if intent.status == 'requires_action' and intent.next_action.type in ['use_stripe_sdk', 'redirect_to_url']:
            ctx = {
                'order': self.order,
                'stripe_settings': StripeSettingsHolder(self.order.event).settings,
            }
            if intent.next_action.type == 'use_stripe_sdk':
                ctx['payment_intent_client_secret'] = intent.client_secret
            elif intent.next_action.type == 'redirect_to_url':
                ctx['payment_intent_next_action_redirect_url'] = intent.next_action.redirect_to_url['url']

            r = render(request, 'pretixplugins/stripe/sca.html', ctx)
            r._csp_ignore = True
            return r
        else:
            try:
                prov._handle_payment_intent(request, self.payment, intent)
            except PaymentException as e:
                messages.error(request, str(e))

            return self._redirect_to_order()


@method_decorator(xframe_options_exempt, 'dispatch')
class ScaReturnView(StripeOrderView, View):
    def get(self, request, *args, **kwargs):
        prov = self.pprov

        try:
            prov._handle_payment_intent(request, self.payment)
        except PaymentException as e:
            messages.error(request, str(e))

        self.order.refresh_from_db()

        return render(request, 'pretixplugins/stripe/sca_return.html', {'order': self.order})


class OrganizerSettingsFormView(DecoupleMixin, OrganizerDetailViewMixin, AdministratorPermissionRequiredMixin, FormView):
    model = Organizer
    permission = 'can_change_organizer_settings'
    form_class = OrganizerStripeSettingsForm
    template_name = 'pretixplugins/stripe/organizer_stripe.html'

    def get_success_url(self):
        return reverse('plugins:stripe:settings.connect', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['obj'] = self.request.organizer
        return kwargs

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            form.save()
            if form.has_changed():
                self.request.organizer.log_action(
                    'pretix.organizer.settings', user=self.request.user, data={
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                )
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)
