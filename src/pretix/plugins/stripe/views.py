#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import logging

import requests
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse
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
from pretix.helpers import OF_SELF
from pretix.helpers.http import redirect_to_url
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.stripe.forms import OrganizerStripeSettingsForm
from pretix.plugins.stripe.models import ReferencedStripeObject
from pretix.plugins.stripe.tasks import (
    get_domain_for_event, stripe_verify_domain,
)

logger = logging.getLogger('pretix.plugins.stripe')


@scopes_disabled()
def oauth_return(request, *args, **kwargs):
    import stripe

    if 'payment_stripe_oauth_event' not in request.session:
        messages.error(request, _('An error occurred during connecting with Stripe, please try again.'))
        return redirect('control:index')

    event = get_object_or_404(Event, pk=request.session['payment_stripe_oauth_event'])

    if request.GET.get('state') != request.session['payment_stripe_oauth_token']:
        messages.error(request, _('An error occurred during connecting with Stripe, please try again.'))
        return redirect_to_url(reverse('control:event.settings.payment.provider', kwargs={
            'organizer': event.organizer.slug,
            'event': event.slug,
            'provider': 'stripe_settings'
        }))

    gs = GlobalSettingsObject()
    testdata = {}

    try:
        resp = requests.post('https://connect.stripe.com/oauth/token', data={
            'grant_type': 'authorization_code',
            'client_secret': (
                gs.settings.payment_stripe_connect_secret_key or gs.settings.payment_stripe_connect_test_secret_key
            ),
            'code': request.GET.get('code')
        })
        data = resp.json()

        if 'error' not in data:
            account = stripe.Account.retrieve(
                data['stripe_user_id'],
                api_key=gs.settings.payment_stripe_connect_secret_key or gs.settings.payment_stripe_connect_test_secret_key
            )
    except:
        logger.exception('Failed to obtain OAuth token')
        messages.error(request, _('An error occurred during connecting with Stripe, please try again.'))
    else:
        if 'error' not in data and data['livemode']:
            try:
                testresp = requests.post('https://connect.stripe.com/oauth/token', data={
                    'grant_type': 'refresh_token',
                    'client_secret': gs.settings.payment_stripe_connect_test_secret_key,
                    'refresh_token': data['refresh_token']
                })
                testdata = testresp.json()
            except:
                logger.exception('Failed to obtain OAuth token')
                messages.error(request, _('An error occurred during connecting with Stripe, please try again.'))
                return redirect_to_url(reverse('control:event.settings.payment.provider', kwargs={
                    'organizer': event.organizer.slug,
                    'event': event.slug,
                    'provider': 'stripe_settings'
                }))

        if 'error' in data:
            messages.error(request, _('Stripe returned an error: {}').format(data['error_description']))
        elif data['livemode'] and 'error' in testdata:
            messages.error(request, _('Stripe returned an error: {}').format(testdata['error_description']))
        else:
            messages.success(request,
                             _('Your Stripe account is now connected to pretix. You can change the settings in '
                               'detail below.'))
            event.settings.payment_stripe_publishable_key = data['stripe_publishable_key']
            # event.settings.payment_stripe_connect_access_token = data['access_token'] we don't need it, right?
            event.settings.payment_stripe_connect_refresh_token = data['refresh_token']
            event.settings.payment_stripe_connect_user_id = data['stripe_user_id']
            event.settings.payment_stripe_merchant_country = account.get('country')
            if (
                account.get('business_profile', {}).get('name')
                or account.get('settings', {}).get('dashboard', {}).get('display_name')
                or account.get('email')
            ):
                event.settings.payment_stripe_connect_user_name = (
                    account.get('business_profile', {}).get('name')
                    or account.get('settings', {}).get('dashboard', {}).get('display_name')
                    or account.get('email')
                )

            if data['livemode']:
                event.settings.payment_stripe_publishable_test_key = testdata['stripe_publishable_key']
            else:
                event.settings.payment_stripe_publishable_test_key = event.settings.payment_stripe_publishable_key

            if request.session.get('payment_stripe_oauth_enable', False):
                event.settings.payment_stripe__enabled = True
                del request.session['payment_stripe_oauth_enable']

            stripe_verify_domain.apply_async(args=(event.pk, get_domain_for_event(event)))

    return redirect_to_url(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': event.organizer.slug,
        'event': event.slug,
        'provider': 'stripe_settings'
    }))


@csrf_exempt
@require_POST
@scopes_disabled()
def webhook(request, *args, **kwargs):
    untrusted_json = json.loads(request.body.decode('utf-8'))
    untrusted_obj = untrusted_json['data']['object']

    # We do not check for the event type as we are not interested in the event it self,
    # we just use it as a trigger to look the charge up to be absolutely sure.
    # Another reason for this is that stripe events are not authenticated, so they could
    # come from anywhere.

    rso_qs = ReferencedStripeObject.objects.select_related('order', 'order__event')

    if untrusted_obj['object'] == "payment_intent":
        pi_id = untrusted_obj['id']
        try:
            rso = rso_qs.get(reference=pi_id)
        except ReferencedStripeObject.DoesNotExist:
            return HttpResponse("Unable to detect event", status=200)
        else:
            return paymentintent_webhook(untrusted_json, pi_id, rso)

    elif untrusted_obj['object'] == "charge":
        charge_id = untrusted_obj['id']
    elif untrusted_obj['object'] == "dispute":
        charge_id = untrusted_obj['charge']
    else:
        return HttpResponse("Not interested in this data type", status=200)

    rso = None
    try:
        rso = rso_qs.get(reference=charge_id)
    except ReferencedStripeObject.DoesNotExist:
        if 'payment_intent' in untrusted_obj:
            # If we receive a charge webhook *before* the payment intent webhook, we don't know the charge ID yet
            # and can't match it -- but we know the payment intent ID! In charge_webhook, we validate that the
            # RSO's pi_id actually matches the pi_id returned by stripe API for the charge.
            try:
                rso = rso_qs.get(reference=untrusted_obj['payment_intent'])
            except ReferencedStripeObject.DoesNotExist:
                pass

    if rso:
        return charge_webhook(untrusted_json, charge_id, rso)
    else:
        # Okay, this is probably not an event that concerns us, maybe other applications talk to the same stripe
        # account
        return HttpResponse("Unable to detect event", status=200)


SOURCE_TYPES = {
    'sofort': 'stripe_sofort',
    'three_d_secure': 'stripe',
    'card': 'stripe',
    'sepa_debit': 'stripe_sepa_debit',
    'giropay': 'stripe_giropay',
    'ideal': 'stripe_ideal',
    'alipay': 'stripe_alipay',
    'bancontact': 'stripe_bancontact',
}


def charge_webhook(untrusted_json, charge_id, rso):
    import stripe

    from pretix.plugins.stripe.payment import StripeCC

    prov = StripeCC(rso.order.event)
    prov._init_api()

    try:
        charge = stripe.Charge.retrieve(
            charge_id,
            expand=['dispute', 'refunds', 'payment_intent', 'payment_intent.latest_charge'],
            **prov.api_kwargs
        )
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(untrusted_json))
        return HttpResponse('Charge not found', status=500)

    metadata = charge['metadata']
    if 'event' not in metadata:
        return HttpResponse('Event not given in charge metadata', status=200)

    if int(metadata['event']) != rso.order.event.pk:
        return HttpResponse('Not interested in this event', status=200)

    # Check the charge we fetched from stripe actually matches our RSO, and as such our own payment and order objects
    allowed_references = [charge.id]
    if getattr(charge, "payment_intent", None):
        allowed_references.append(charge.payment_intent.id)
    if rso.reference not in allowed_references:
        return HttpResponse('Charge mismatched', status=200)

    order = rso.payment.order
    payment = rso.payment

    with transaction.atomic():
        payment = OrderPayment.objects.select_for_update(of=OF_SELF).get(pk=payment.pk)

        if payment.provider != prov.identifier:
            prov = payment.payment_provider
            prov._init_api()

        order.log_action('pretix.plugins.stripe.event', data=untrusted_json)

        is_refund = charge['amount_refunded'] or charge['refunds']['total_count'] or charge['dispute']
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
                if getattr(charge, "payment_intent", None):
                    payment.info = str(charge.payment_intent)
                payment.confirm()
            except LockTimeoutException:
                return HttpResponse("Lock timeout, please try again.", status=503)
            except Quota.QuotaExceededException:
                pass
        elif charge['status'] == 'failed' and payment.state in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED):
            payment.fail(info=str(charge))

    return HttpResponse(status=200)


def paymentintent_webhook(untrusted_json, paymentintent_id, rso):
    import stripe

    from pretix.plugins.stripe.payment import StripeCC

    prov = StripeCC(rso.order.event)
    prov._init_api()

    try:
        paymentintent = stripe.PaymentIntent.retrieve(paymentintent_id, expand=["latest_charge"], **prov.api_kwargs)
    except stripe.error.StripeError:
        logger.exception('Stripe error on webhook. Event data: %s' % str(untrusted_json))
        return HttpResponse('Charge not found', status=500)

    if paymentintent.latest_charge:
        ReferencedStripeObject.objects.get_or_create(
            reference=paymentintent.latest_charge.id,
            defaults={'order': rso.payment.order, 'payment': rso.payment}
        )

    # We consider the risk acceptable that someone who knows the payment intent ID can
    # mark a pending payment as failed, therefore we 'trust' the event type here:
    if untrusted_json["type"] == "payment_intent.payment_failed":
        rso.payment.fail(info=str(paymentintent), log_data=untrusted_json)

    return HttpResponse(status=200)


@event_permission_required('event.settings.payment:write')
def oauth_disconnect(request, **kwargs):
    if request.method != "POST":
        return render(request, 'pretixplugins/stripe/oauth_disconnect.html', {})

    del request.event.settings.payment_stripe_publishable_key
    del request.event.settings.payment_stripe_publishable_test_key
    del request.event.settings.payment_stripe_connect_access_token
    del request.event.settings.payment_stripe_connect_refresh_token
    del request.event.settings.payment_stripe_connect_user_id
    del request.event.settings.payment_stripe_connect_user_name
    request.event.settings.payment_stripe__enabled = False
    messages.success(request, _('Your Stripe account has been disconnected.'))

    return redirect_to_url(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
        'provider': 'stripe_settings'
    }))


class StripeOrderView:
    def dispatch(self, request, *args, **kwargs):
        try:
            self.order = request.event.orders.get_with_secret_check(
                code=kwargs['order'], received_secret=kwargs['hash'].lower(), tag='plugins:stripe'
            )
        except Order.DoesNotExist:
            raise Http404('Unknown order')
        self.payment = get_object_or_404(
            self.order.payments,
            pk=self.kwargs['payment'],
            provider__startswith='stripe'
        )
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def pprov(self):
        return self.request.event.get_payment_providers()[self.payment.provider]

    def _redirect_to_order(self):
        return redirect_to_url(eventreverse(self.request.event, 'presale:event.order', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        }) + ('?paid=yes' if self.order.status == Order.STATUS_PAID else ''))


@method_decorator(xframe_options_exempt, 'dispatch')
class ScaView(StripeOrderView, View):

    def get(self, request, *args, **kwargs):
        import stripe

        from pretix.plugins.stripe.payment import StripeSettingsHolder

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
                    expand=["latest_charge"],
                    **prov.api_kwargs
                )
            except stripe.error.InvalidRequestError:
                logger.exception('Could not retrieve payment intent')
                messages.error(self.request, _('Sorry, there was an error in the payment process.'))
                return self._redirect_to_order()
        else:
            messages.error(self.request, _('Sorry, there was an error in the payment process.'))
            return self._redirect_to_order()

        if intent.status == 'requires_action' and intent.next_action.type in [
            'use_stripe_sdk', 'redirect_to_url', 'alipay_handle_redirect', 'wechat_pay_display_qr_code',
            'swish_handle_redirect_or_display_qr_code', 'multibanco_display_details', 'promptpay_display_qr_code',
        ]:
            ctx = {
                'order': self.order,
                'stripe_settings': StripeSettingsHolder(self.order.event).settings,
            }
            ctx['payment_intent_action_type'] = intent.next_action.type
            if intent.next_action.type in ('use_stripe_sdk', 'alipay_handle_redirect', 'wechat_pay_display_qr_code'):
                ctx['payment_intent_client_secret'] = intent.client_secret
            elif intent.next_action.type == 'redirect_to_url':
                ctx['payment_intent_next_action_redirect_url'] = intent.next_action.redirect_to_url['url']
                ctx['payment_intent_redirect_action_handling'] = prov.redirect_action_handling
            elif intent.next_action.type == 'swish_handle_redirect_or_display_qr_code':
                ctx['payment_intent_next_action_redirect_url'] = intent.next_action.swish_handle_redirect_or_display_qr_code['hosted_instructions_url']
                ctx['payment_intent_redirect_action_handling'] = 'iframe'
            elif intent.next_action.type == 'multibanco_display_details':
                ctx['payment_intent_next_action_redirect_url'] = intent.next_action.multibanco_display_details['hosted_voucher_url']
                ctx['payment_intent_redirect_action_handling'] = 'iframe'
            elif intent.next_action.type == 'promptpay_display_qr_code':
                ctx['payment_intent_promptpay_image_url'] = intent.next_action.promptpay_display_qr_code['image_url_svg']

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
        ctx = {
            'order': self.order,
            'payment_intent_redirect_action_handling': prov.redirect_action_handling,
            'order_url': eventreverse(self.request.event, 'presale:event.order', kwargs={
                'order': self.order.code,
                'secret': self.order.secret
            }),
        }

        return render(request, 'pretixplugins/stripe/sca_return.html', ctx)


class OrganizerSettingsFormView(DecoupleMixin, OrganizerDetailViewMixin, AdministratorPermissionRequiredMixin, FormView):
    model = Organizer
    permission = 'organizer.settings.general:write'
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
            return redirect_to_url(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)
