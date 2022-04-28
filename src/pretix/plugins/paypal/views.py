#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
# This file contains Apache-licensed contributions copyrighted by: Flavia Bastos
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import hashlib
import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.core import signing
from django.db.models import Sum
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django_scopes import scopes_disabled
from paypalcheckoutsdk import orders as pp_orders, payments as pp_payments

from pretix.base.models import Event, Order, OrderPayment, OrderRefund, Quota
from pretix.base.payment import PaymentException
from pretix.base.settings import GlobalSettingsObject
from pretix.control.permissions import event_permission_required
from pretix.multidomain.urlreverse import eventreverse
from pretix.plugins.paypal.client.customer.partners_merchantintegrations_get_request import (
    PartnersMerchantIntegrationsGetRequest,
)
from pretix.plugins.paypal.models import ReferencedPayPalObject
from pretix.plugins.paypal.payment import PaypalMethod, PaypalMethod as Paypal
from pretix.presale.views import get_cart, get_cart_total

logger = logging.getLogger('pretix.plugins.paypal')


class PaypalOrderView:
    def dispatch(self, request, *args, **kwargs):
        try:
            self.order = request.event.orders.get(code=kwargs['order'])
            if hashlib.sha1(self.order.secret.lower().encode()).hexdigest() != kwargs['hash'].lower():
                raise Http404('Unknown order')
        except Order.DoesNotExist:
            # Do a hash comparison as well to harden timing attacks
            if 'abcdefghijklmnopq'.lower() == hashlib.sha1('abcdefghijklmnopq'.encode()).hexdigest():
                raise Http404('Unknown order')
            else:
                raise Http404('Unknown order')
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def payment(self):
        return get_object_or_404(
            self.order.payments,
            pk=self.kwargs['payment'],
            provider__istartswith='paypal',
        )

    def _redirect_to_order(self):
        return redirect(eventreverse(self.request.event, 'presale:event.order', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        }) + ('?paid=yes' if self.order.status == Order.STATUS_PAID else ''))


@xframe_options_exempt
def redirect_view(request, *args, **kwargs):
    signer = signing.Signer(salt='safe-redirect')
    try:
        url = signer.unsign(request.GET.get('url', ''))
    except signing.BadSignature:
        return HttpResponseBadRequest('Invalid parameter')

    r = render(request, 'pretixplugins/paypal/redirect.html', {
        'url': url,
    })
    r._csp_ignore = True
    return r


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(xframe_options_exempt, 'dispatch')
class XHRView(TemplateView):
    template_name = ''

    def post(self, request, *args, **kwargs):
        if 'order' in self.kwargs:
            order = self.request.event.orders.filter(code=self.kwargs['order']).select_related('event').first()
            if order:
                if order.secret.lower() == self.kwargs['secret'].lower():
                    pass
                else:
                    order = None
        else:
            order = None

        prov = PaypalMethod(request.event)

        if order:
            lp = order.payments.last()
            if lp and lp.state not in (OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED):
                fee = lp.fee.value - prov.calculate_fee(order.pending_sum - lp.fee.value)
            else:
                fee = prov.calculate_fee(order.pending_sum)

            cart = {
                'positions': order.positions,
                'total': order.pending_sum,
                'fee': fee,
            }
        else:
            cart = {
                'positions': get_cart(request),
                'total': get_cart_total(request),
                'fee': prov.calculate_fee(get_cart_total(request)),
            }

        paypal_order = prov._create_paypal_order(request, None, cart)
        r = JsonResponse(paypal_order.dict())
        r._csp_ignore = True
        return r


@method_decorator(xframe_options_exempt, 'dispatch')
class PayView(PaypalOrderView, TemplateView):
    template_name = ''

    def get(self, request, *args, **kwargs):
        if self.payment.state != OrderPayment.PAYMENT_STATE_CREATED:
            return self._redirect_to_order()
        else:
            r = render(request, 'pretixplugins/paypal/pay.html', self.get_context_data())
            return r

    def post(self, request, *args, **kwargs):
        self.payment.payment_provider.execute_payment(request, self.payment)
        return self._redirect_to_order()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['order'] = self.order
        ctx['oid'] = self.payment.info_data['id']
        ctx['method'] = self.payment.payment_provider.method
        return ctx


@scopes_disabled()
@event_permission_required('can_change_event_settings')
def isu_return(request, *args, **kwargs):
    getparams = ['merchantId', 'merchantIdInPayPal', 'permissionsGranted', 'accountStatus', 'consentStatus', 'productIntentID', 'isEmailConfirmed']
    sessionparams = ['payment_paypal_isu_event', 'payment_paypal_isu_tracking_id']
    if not any(k in request.GET for k in getparams) or not any(k in request.session for k in sessionparams):
        messages.error(request, _('An error occurred during connecting with PayPal, please try again.'))
        return redirect(reverse('control:index'))

    event = get_object_or_404(Event, pk=request.session['payment_paypal_isu_event'])

    gs = GlobalSettingsObject()
    prov = Paypal(event)
    prov.init_api()

    try:
        req = PartnersMerchantIntegrationsGetRequest(
            gs.settings.get('payment_paypal_connect_partner_merchant_id'),
            request.GET.get('merchantIdInPayPal')
        )
        response = prov.client.execute(req)
    except IOError as e:
        messages.error(request, _('An error occurred during connecting with PayPal, please try again.'))
        logger.exception('PayPal PartnersMerchantIntegrationsGetRequest: {}'.format(str(e)))
    else:
        params = ['merchant_id', 'tracking_id', 'payments_receivable', 'primary_email_confirmed']
        if not any(k in response.result for k in params):
            if 'message' in response.result:
                messages.error(request, response.result.message)
            else:
                messages.error(request, _('An error occurred during connecting with PayPal, please try again.'))
        else:
            if response.result.tracking_id != request.session['payment_paypal_isu_tracking_id']:
                messages.error(request, _('An error occurred during connecting with PayPal, please try again.'))
            else:
                if request.GET.get("isEmailConfirmed") == "false":  # Yes - literal!
                    messages.warning(
                        request,
                        _('The e-mail address on your PayPal account has not yet been confirmed. You will need to do '
                          'this before you can start accepting payments.')
                    )
                messages.success(
                    request,
                    _('Your PayPal account is now connected to pretix. You can change the settings in detail below.')
                )

                event.settings.payment_paypal_isu_merchant_id = response.result.merchant_id

                # Just for good measure: Let's keep a copy of the granted scopes
                for integration in response.result.oauth_integrations:
                    if integration.integration_type == 'OAUTH_THIRD_PARTY':
                        for third_party in integration.oauth_third_party:
                            if third_party.partner_client_id == prov.client.environment.client_id:
                                event.settings.payment_paypal_isu_scopes = third_party.scopes

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': event.organizer.slug,
        'event': event.slug,
        'provider': 'paypal_settings'
    }))


def success(request, *args, **kwargs):
    token = request.GET.get('token')
    payer = request.GET.get('PayerID')
    request.session['payment_paypal_token'] = token
    request.session['payment_paypal_payer'] = payer

    urlkwargs = {}
    if 'cart_namespace' in kwargs:
        urlkwargs['cart_namespace'] = kwargs['cart_namespace']

    if request.session.get('payment_paypal_payment'):
        payment = OrderPayment.objects.get(pk=request.session.get('payment_paypal_payment'))
    else:
        payment = None

    if request.session.get('payment_paypal_id', None):
        if payment:
            prov = Paypal(request.event)
            try:
                resp = prov.execute_payment(request, payment)
            except PaymentException as e:
                messages.error(request, str(e))
                urlkwargs['step'] = 'payment'
                return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs=urlkwargs))
            if resp:
                return resp
    else:
        messages.error(request, _('Invalid response from PayPal received.'))
        logger.error('Session did not contain payment_paypal_id')
        urlkwargs['step'] = 'payment'
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs=urlkwargs))

    if payment:
        return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
            'order': payment.order.code,
            'secret': payment.order.secret
        }) + ('?paid=yes' if payment.order.status == Order.STATUS_PAID else ''))
    else:
        urlkwargs['step'] = 'confirm'
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs=urlkwargs))


def abort(request, *args, **kwargs):
    messages.error(request, _('It looks like you canceled the PayPal payment'))

    if request.session.get('payment_paypal_payment'):
        payment = OrderPayment.objects.get(pk=request.session.get('payment_paypal_payment'))
    else:
        payment = None

    if payment:
        return redirect(eventreverse(request.event, 'presale:event.order', kwargs={
            'order': payment.order.code,
            'secret': payment.order.secret
        }) + ('?paid=yes' if payment.order.status == Order.STATUS_PAID else ''))
    else:
        return redirect(eventreverse(request.event, 'presale:event.checkout', kwargs={'step': 'payment'}))


@csrf_exempt
@require_POST
@scopes_disabled()
def webhook(request, *args, **kwargs):
    event_body = request.body.decode('utf-8').strip()
    event_json = json.loads(event_body)

    # We do not check the signature, we just use it as a trigger to look the charge up.
    if 'resource_type' not in event_json:
        return HttpResponse("Invalid body, no resource_type given", status=400)

    if event_json['resource_type'] not in ["checkout-order", "refund", "capture"]:
        return HttpResponse("Not interested in this resource type", status=200)

    # Retrieve the Charge ID of the refunded payment
    if event_json['resource_type'] == 'refund':
        payloadid = get_link(event_json['resource']['links'], 'up')['href'].split('/')[-1]
    else:
        payloadid = event_json['resource']['id']

    refs = [payloadid]
    if event_json['resource'].get('supplementary_data', {}).get('related_ids', {}).get('order_id'):
        refs.append(event_json['resource'].get('supplementary_data').get('related_ids').get('order_id'))

    rso = ReferencedPayPalObject.objects.select_related('order', 'order__event').filter(
        reference__in=refs
    ).first()
    if rso:
        event = rso.order.event
    else:
        rso = None
        if hasattr(request, 'event'):
            event = request.event
        else:
            return HttpResponse("Unable to detect event", status=200)

    prov = Paypal(event)
    prov.init_api()

    try:
        if rso:
            payloadid = rso.payment.info_data['id']
        sale = prov.client.execute(pp_orders.OrdersGetRequest(payloadid)).result
    except IOError:
        logger.exception('PayPal error on webhook. Event data: %s' % str(event_json))
        return HttpResponse('Sale not found', status=500)

    if rso and rso.payment:
        payment = rso.payment
    else:
        payments = OrderPayment.objects.filter(order__event=event, provider='paypal',
                                               info__icontains=sale['id'])
        payment = None
        for p in payments:
            # Legacy PayPal info-data
            if "purchase_units" not in p.info_data:
                try:
                    req = pp_orders.OrdersGetRequest(p.info_data['cart'])
                    response = prov.client.execute(req)
                    p.info = json.dumps(response.result.dict())
                    p.save(update_fields=['info'])
                    p.refresh_from_db()
                except IOError:
                    logger.exception('PayPal error on webhook. Event data: %s' % str(event_json))
                    return HttpResponse('Could not retrieve Order Data', status=500)

            for res in p.info_data['purchase_units'][0]['payments']['captures']:
                if res['status'] in ['COMPLETED', 'PARTIALLY_REFUNDED'] and res['id'] == sale['id']:
                    payment = p
                    break

    if not payment:
        return HttpResponse('Payment not found', status=200)

    payment.order.log_action('pretix.plugins.paypal.event', data=event_json)

    if payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED and sale['status'] in ('PARTIALLY_REFUNDED', 'REFUNDED', 'COMPLETED'):
        if event_json['resource_type'] == 'refund':
            try:
                req = pp_payments.RefundsGetRequest(event_json['resource']['id'])
                refund = prov.client.execute(req).result
            except IOError:
                logger.exception('PayPal error on webhook. Event data: %s' % str(event_json))
                return HttpResponse('Refund not found', status=500)

            known_refunds = {r.info_data.get('id'): r for r in payment.refunds.all()}
            if refund['id'] not in known_refunds:
                payment.create_external_refund(
                    amount=abs(Decimal(refund['amount']['value'])),
                    info=json.dumps(refund.dict() if not isinstance(refund, dict) else refund)
                )
            elif known_refunds.get(refund['id']).state in (
                    OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT) and refund['status'] == 'COMPLETED':
                known_refunds.get(refund['id']).done()

            if 'seller_payable_breakdown' in refund and 'total_refunded_amount' in refund['seller_payable_breakdown']:
                known_sum = payment.refunds.filter(
                    state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                               OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_SOURCE_EXTERNAL)
                ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
                total_refunded_amount = Decimal(refund['seller_payable_breakdown']['total_refunded_amount']['value'])
                if known_sum < total_refunded_amount:
                    payment.create_external_refund(
                        amount=total_refunded_amount - known_sum
                    )
        elif sale['status'] == 'REFUNDED':
            known_sum = payment.refunds.filter(
                state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                           OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_SOURCE_EXTERNAL)
            ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            if known_sum < payment.amount:
                payment.create_external_refund(
                    amount=payment.amount - known_sum
                )
    elif payment.state in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED,
                           OrderPayment.PAYMENT_STATE_CANCELED, OrderPayment.PAYMENT_STATE_FAILED) \
            and sale['status'] == 'COMPLETED':
        try:
            payment.confirm()
        except Quota.QuotaExceededException:
            pass

    return HttpResponse(status=200)


@event_permission_required('can_change_event_settings')
@require_POST
def isu_disconnect(request, **kwargs):
    del request.event.settings.payment_paypal_connect_refresh_token
    del request.event.settings.payment_paypal_connect_user_id
    del request.event.settings.payment_paypal_isu_merchant_id
    del request.event.settings.payment_paypal_isu_scopes
    request.event.settings.payment_paypal__enabled = False
    messages.success(request, _('Your PayPal account has been disconnected.'))

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
        'provider': 'paypal_settings'
    }))


def get_link(links, rel):
    for link in links:
        if link['rel'] == rel:
            return link

    return None
