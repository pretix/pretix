import hashlib
import json
import logging
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Union

import pytz
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.dispatch import receiver
from django.forms import Form
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_countries import Countries
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput
from i18nfield.strings import LazyI18nString

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms import PlaceholderValidator
from pretix.base.models import (
    CartPosition, Event, GiftCard, InvoiceAddress, Order, OrderPayment,
    OrderRefund, Quota,
)
from pretix.base.reldate import RelativeDateField, RelativeDateWrapper
from pretix.base.settings import SettingsSandbox
from pretix.base.signals import register_payment_providers
from pretix.base.templatetags.money import money_filter
from pretix.base.templatetags.rich_text import rich_text
from pretix.helpers.money import DecimalTextInput
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.presale.views import get_cart, get_cart_total
from pretix.presale.views.cart import cart_session, get_or_create_cart_id

logger = logging.getLogger(__name__)


class PaymentProviderForm(Form):
    def clean(self):
        cleaned_data = super().clean()
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and not val:
                self.add_error(k, _('This field is required.'))


class BasePaymentProvider:
    """
    This is the base class for all payment providers.
    """

    def __init__(self, event: Event):
        self.event = event
        self.settings = SettingsSandbox('payment', self.identifier, event)
        # Default values
        if self.settings.get('_fee_reverse_calc') is None:
            self.settings.set('_fee_reverse_calc', True)

    def __str__(self):
        return self.identifier

    def is_implicit(self, request: HttpRequest) -> bool:
        """
        Returns whether or whether not this payment provider is an "implicit" payment provider that will
        *always* and unconditionally be used if is_allowed() returns True and does not require any input.
        This is  intended to be used by the FreeOrderProvider, which skips the payment choice page.
        By default, this returns ``False``. Please do not set this if you don't know exactly what you are doing.
        """
        return False

    @property
    def is_meta(self) -> bool:
        """
        Returns whether or whether not this payment provider is a "meta" payment provider that only
        works as a settings holder for other payment providers and should never be used directly. This
        is a trick to implement payment gateways with multiple payment methods but unified payment settings.
        Take a look at the built-in stripe provider to see how this might be used.
        By default, this returns ``False``.
        """
        return False

    @property
    def priority(self) -> int:
        """
        Returns a priority that is used for sorting payment providers. Higher priority means higher up in the list.
        Default to 100. Providers with same priority are sorted alphabetically.
        """
        return 100

    @property
    def is_enabled(self) -> bool:
        """
        Returns whether or whether not this payment provider is enabled.
        By default, this is determined by the value of the ``_enabled`` setting.
        """
        return self.settings.get('_enabled', as_type=bool)

    @property
    def test_mode_message(self) -> str:
        """
        If this property is set to a string, this will be displayed when this payment provider is selected
        while the event is in test mode. You should use it to explain to your user how your plugin behaves,
        e.g. if it falls back to a test mode automatically as well or if actual payments will be performed.

        If you do not set this (or, return ``None``), pretix will show a default message warning the user
        that this plugin does not support test mode payments.
        """
        return None

    def calculate_fee(self, price: Decimal) -> Decimal:
        """
        Calculate the fee for this payment provider which will be added to
        final price before fees (but after taxes). It should include any taxes.
        The default implementation makes use of the setting ``_fee_abs`` for an
        absolute fee and ``_fee_percent`` for a percentage.

        :param price: The total value without the payment method fee, after taxes.
        """
        fee_abs = self.settings.get('_fee_abs', as_type=Decimal, default=0)
        fee_percent = self.settings.get('_fee_percent', as_type=Decimal, default=0)
        fee_reverse_calc = self.settings.get('_fee_reverse_calc', as_type=bool, default=True)
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
        if fee_reverse_calc:
            return ((price + fee_abs) * (1 / (1 - fee_percent / 100)) - price).quantize(
                Decimal('1') / 10 ** places, ROUND_HALF_UP
            )
        else:
            return (price * fee_percent / 100 + fee_abs).quantize(
                Decimal('1') / 10 ** places, ROUND_HALF_UP
            )

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this payment provider. This should
        be short but self-explaining. Good examples include 'Bank transfer'
        and 'Credit card via Stripe'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def public_name(self) -> str:
        """
        A human-readable name for this payment provider to be shown to the public.
        This should be short but self-explaining. Good examples include 'Bank transfer'
        and 'Credit card', but 'Credit card via Stripe' might be to explicit. By default,
        this is the same as ``verbose_name``
        """
        return self.verbose_name

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this payment provider.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def abort_pending_allowed(self) -> bool:
        """
        Whether or not a user can abort a payment in pending start to switch to another
        payment method. This returns ``False`` by default which is no guarantee that
        aborting a pending payment can never happen, it just hides the frontend button
        to avoid users accidentally committing double payments.
        """
        return False

    @property
    def settings_form_fields(self) -> dict:
        """
        When the event's administrator visits the event configuration
        page, this method is called to return the configuration fields available.

        It should therefore return a dictionary where the keys should be (unprefixed)
        settings keys and the values should be corresponding Django form fields.

        The default implementation returns the appropriate fields for the ``_enabled``,
        ``_fee_abs``, ``_fee_percent`` and ``_availability_date`` settings mentioned above.

        We suggest that you return an ``OrderedDict`` object instead of a dictionary
        and make use of the default implementation. Your implementation could look
        like this::

            @property
            def settings_form_fields(self):
                return OrderedDict(
                    list(super().settings_form_fields.items()) + [
                        ('bank_details',
                         forms.CharField(
                             widget=forms.Textarea,
                             label=_('Bank account details'),
                             required=False
                         ))
                    ]
                )

        .. WARNING:: It is highly discouraged to alter the ``_enabled`` field of the default
                     implementation.
        """
        places = settings.CURRENCY_PLACES.get(self.event.currency, 2)

        if not self.settings.get('_hidden_seed'):
            self.settings.set('_hidden_seed', get_random_string(64))
        hidden_url = build_absolute_uri(self.event, 'presale:event.payment.unlock', kwargs={
            'hash': hashlib.sha256((self.settings._hidden_seed + self.event.slug).encode()).hexdigest(),
        })

        d = OrderedDict([
            ('_enabled',
             forms.BooleanField(
                 label=_('Enable payment method'),
                 required=False,
             )),
            ('_availability_date',
             RelativeDateField(
                 label=_('Available until'),
                 help_text=_('Users will not be able to choose this payment provider after the given date.'),
                 required=False,
             )),
            ('_invoice_text',
             I18nFormField(
                 label=_('Text on invoices'),
                 help_text=_('Will be printed just below the payment figures and above the closing text on invoices. '
                             'This will only be used if the invoice is generated before the order is paid. If the '
                             'invoice is generated later, it will show a text stating that it has already been paid.'),
                 required=False,
                 widget=I18nTextarea,
                 widget_kwargs={'attrs': {'rows': '2'}}
             )),
            ('_total_min',
             forms.DecimalField(
                 label=_('Minimum order total'),
                 help_text=_('This payment will be available only if the order total is equal to or exceeds the given '
                             'value. The order total for this purpose may be computed without taking the fees imposed '
                             'by this payment method into account.'),
                 localize=True,
                 required=False,
                 decimal_places=places,
                 widget=DecimalTextInput(places=places)
             )),
            ('_total_max',
             forms.DecimalField(
                 label=_('Maximum order total'),
                 help_text=_('This payment will be available only if the order total is equal to or below the given '
                             'value. The order total for this purpose may be computed without taking the fees imposed '
                             'by this payment method into account.'),
                 localize=True,
                 required=False,
                 decimal_places=places,
                 widget=DecimalTextInput(places=places)
             )),
            ('_fee_abs',
             forms.DecimalField(
                 label=_('Additional fee'),
                 help_text=_('Absolute value'),
                 localize=True,
                 required=False,
                 decimal_places=places,
                 widget=DecimalTextInput(places=places)
             )),
            ('_fee_percent',
             forms.DecimalField(
                 label=_('Additional fee'),
                 help_text=_('Percentage of the order total.'),
                 localize=True,
                 required=False,
             )),
            ('_fee_reverse_calc',
             forms.BooleanField(
                 label=_('Calculate the fee from the total value including the fee.'),
                 help_text=_('We recommend to enable this if you want your users to pay the payment fees of your '
                             'payment provider. <a href="{docs_url}" target="_blank" rel="noopener">Click here '
                             'for detailed information on what this does.</a> Don\'t forget to set the correct fees '
                             'above!').format(docs_url='https://docs.pretix.eu/en/latest/user/payments/fees.html'),
                 required=False
             )),
            ('_restricted_countries',
             forms.MultipleChoiceField(
                 label=_('Restrict to countries'),
                 choices=Countries(),
                 help_text=_('Only allow choosing this payment provider for invoice addresses in the selected '
                             'countries. If you don\'t select any country, all countries are allowed. This is only '
                             'enabled if the invoice address is required.'),
                 widget=forms.CheckboxSelectMultiple(
                     attrs={'class': 'scrolling-multiple-choice'}
                 ),
                 required=False,
                 disabled=not self.event.settings.invoice_address_required
             )),
            ('_restrict_to_sales_channels',
             forms.MultipleChoiceField(
                 label=_('Restrict to specific sales channels'),
                 choices=(
                     (c.identifier, c.verbose_name) for c in get_all_sales_channels().values()
                     if c.payment_restrictions_supported
                 ),
                 initial=['web'],
                 widget=forms.CheckboxSelectMultiple,
                 help_text=_(
                     'Only allow the usage of this payment provider in the following sales channels'),
             )),
            ('_hidden',
             forms.BooleanField(
                 label=_('Hide payment method'),
                 required=False,
                 help_text=_(
                     'The payment method will not be shown by default but only to people who enter the shop through '
                     'a special link.'
                 ),
             )),
            ('_hidden_url',
             forms.URLField(
                 label=_('Link to enable payment method'),
                 widget=forms.TextInput(attrs={
                     'readonly': 'readonly',
                     'data-display-dependency': '#id_%s_hidden' % self.settings.get_prefix(),
                     'value': hidden_url,
                 }),
                 required=False,
                 initial=hidden_url,
                 help_text=_(
                     'Share this link with customers who should use this payment method.'
                 ),
             )),
        ])
        d['_restricted_countries']._as_type = list
        d['_restrict_to_sales_channels']._as_type = list
        return d

    def settings_form_clean(self, cleaned_data):
        """
        Overriding this method allows you to inject custom validation into the settings form.

        :param cleaned_data: Form data as per previous validations.
        :return: Please return the modified cleaned_data
        """
        return cleaned_data

    def settings_content_render(self, request: HttpRequest) -> str:
        """
        When the event's administrator visits the event configuration
        page, this method is called. It may return HTML containing additional information
        that is displayed below the form fields configured in ``settings_form_fields``.
        """
        return ""

    def render_invoice_text(self, order: Order, payment: OrderPayment) -> str:
        """
        This is called when an invoice for an order with this payment provider is generated.
        The default implementation returns the content of the _invoice_text configuration
        variable (an I18nString), or an empty string if unconfigured. For paid orders, the
        default implementation always renders a string stating that the invoice is already paid.
        """
        if order.status == Order.STATUS_PAID:
            return pgettext_lazy('invoice', 'The payment for this invoice has already been received.')
        return self.settings.get('_invoice_text', as_type=LazyI18nString, default='')

    @property
    def payment_form_fields(self) -> dict:
        """
        This is used by the default implementation of :py:meth:`payment_form`.
        It should return an object similar to :py:attr:`settings_form_fields`.

        The default implementation returns an empty dictionary.
        """
        return {}

    def payment_form(self, request: HttpRequest) -> Form:
        """
        This is called by the default implementation of :py:meth:`payment_form_render`
        to obtain the form that is displayed to the user during the checkout
        process. The default implementation constructs the form using
        :py:attr:`payment_form_fields` and sets appropriate prefixes for the form
        and all fields and fills the form with data form the user's session.

        If you overwrite this, we strongly suggest that you inherit from
        ``PaymentProviderForm`` (from this module) that handles some nasty issues about
        required fields for you.
        """
        form = PaymentProviderForm(
            data=(request.POST if request.method == 'POST' and request.POST.get("payment") == self.identifier else None),
            prefix='payment_%s' % self.identifier,
            initial={
                k.replace('payment_%s_' % self.identifier, ''): v
                for k, v in request.session.items()
                if k.startswith('payment_%s_' % self.identifier)
            }
        )
        form.fields = self.payment_form_fields

        for k, v in form.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False

        return form

    def _is_still_available(self, now_dt=None, cart_id=None, order=None):
        now_dt = now_dt or now()
        tz = pytz.timezone(self.event.settings.timezone)

        availability_date = self.settings.get('_availability_date', as_type=RelativeDateWrapper)
        if availability_date:
            if self.event.has_subevents and cart_id:
                availability_date = min([
                    availability_date.datetime(se).date()
                    for se in self.event.subevents.filter(
                        id__in=CartPosition.objects.filter(
                            cart_id=cart_id, event=self.event
                        ).values_list('subevent', flat=True)
                    )
                ])
            elif self.event.has_subevents and order:
                availability_date = min([
                    availability_date.datetime(se).date()
                    for se in self.event.subevents.filter(
                        id__in=order.positions.values_list('subevent', flat=True)
                    )
                ])
            elif self.event.has_subevents:
                logger.error('Payment provider is not subevent-ready.')
                return False
            else:
                availability_date = availability_date.datetime(self.event).date()

            return availability_date >= now_dt.astimezone(tz).date()

        return True

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        """
        You can use this method to disable this payment provider for certain groups
        of users, products or other criteria. If this method returns ``False``, the
        user will not be able to select this payment method. This will only be called
        during checkout, not on retrying.

        The default implementation checks for the _availability_date setting to be either unset or in the future
        and for the _total_max and _total_min requirements to be met. It also checks the ``_restrict_countries``
        and ``_restrict_to_sales_channels`` setting.

        :param total: The total value without the payment method fee, after taxes.

        .. versionchanged:: 1.17.0

           The ``total`` parameter has been added. For backwards compatibility, this method is called again
           without this parameter if it raises a ``TypeError`` on first try.
        """
        timing = self._is_still_available(cart_id=get_or_create_cart_id(request))
        pricing = True

        if (self.settings._total_max is not None or self.settings._total_min is not None) and total is None:
            raise ImproperlyConfigured('This payment provider does not support maximum or minimum amounts.')

        if self.settings._total_max is not None:
            pricing = pricing and total <= Decimal(self.settings._total_max)

        if self.settings._total_min is not None:
            pricing = pricing and total >= Decimal(self.settings._total_min)

        if self.settings.get('_hidden', as_type=bool):
            hashes = request.session.get('pretix_unlock_hashes', [])
            if hashlib.sha256((self.settings._hidden_seed + self.event.slug).encode()).hexdigest() not in hashes:
                return False

        def get_invoice_address():
            if not hasattr(request, '_checkout_flow_invoice_address'):
                cs = cart_session(request)
                iapk = cs.get('invoice_address')
                if not iapk:
                    request._checkout_flow_invoice_address = InvoiceAddress()
                else:
                    try:
                        request._checkout_flow_invoice_address = InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
                    except InvoiceAddress.DoesNotExist:
                        request._checkout_flow_invoice_address = InvoiceAddress()
            return request._checkout_flow_invoice_address

        if self.event.settings.invoice_address_required:
            restricted_countries = self.settings.get('_restricted_countries', as_type=list)
            if restricted_countries:
                ia = get_invoice_address()
                if str(ia.country) not in restricted_countries:
                    return False

        if hasattr(request, 'sales_channel') and request.sales_channel.identifier not in \
                self.settings.get('_restrict_to_sales_channels', as_type=list, default=['web']):
            return False

        return timing and pricing

    def payment_form_render(self, request: HttpRequest, total: Decimal) -> str:
        """
        When the user selects this provider as their preferred payment method,
        they will be shown the HTML you return from this method.

        The default implementation will call :py:meth:`payment_form`
        and render the returned form. If your payment method doesn't require
        the user to fill out form fields, you should just return a paragraph
        of explanatory text.
        """
        form = self.payment_form(request)
        template = get_template('pretixpresale/event/checkout_payment_form_default.html')
        ctx = {'request': request, 'form': form}
        return template.render(ctx)

    def checkout_confirm_render(self, request) -> str:
        """
        If the user has successfully filled in their payment data, they will be redirected
        to a confirmation page which lists all details of their order for a final review.
        This method should return the HTML which should be displayed inside the
        'Payment' box on this page.

        In most cases, this should include a short summary of the user's input and
        a short explanation on how the payment process will continue.
        """
        raise NotImplementedError()  # NOQA

    def payment_pending_render(self, request: HttpRequest, payment: OrderPayment) -> str:
        """
        Render customer-facing instructions on how to proceed with a pending payment

        :return: HTML
        """
        return ""

    def checkout_prepare(self, request: HttpRequest, cart: Dict[str, Any]) -> Union[bool, str]:
        """
        Will be called after the user selects this provider as their payment method.
        If you provided a form to the user to enter payment data, this method should
        at least store the user's input into their session.

        This method should return ``False`` if the user's input was invalid, ``True``
        if the input was valid and the frontend should continue with default behavior
        or a string containing a URL if the user should be redirected somewhere else.

        On errors, you should use Django's message framework to display an error message
        to the user (or the normal form validation error messages).

        The default implementation stores the input into the form returned by
        :py:meth:`payment_form` in the user's session.

        If your payment method requires you to redirect the user to an external provider,
        this might be the place to do so.

        .. IMPORTANT:: If this is called, the user has not yet confirmed their order.
           You may NOT do anything which actually moves money.

        :param cart: This dictionary contains at least the following keys:

            positions:
               A list of ``CartPosition`` objects that are annotated with the special
               attributes ``count`` and ``total`` because multiple objects of the
               same content are grouped into one.

            raw:
                The raw list of ``CartPosition`` objects in the users cart

            total:
                The overall total *including* the fee for the payment method.

            payment_fee:
                The fee for the payment method.
        """
        form = self.payment_form(request)
        if form.is_valid():
            for k, v in form.cleaned_data.items():
                request.session['payment_%s_%s' % (self.identifier, k)] = v
            return True
        else:
            return False

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        """
        This is called at the time the user tries to place the order. It should return
        ``True`` if the user's session is valid and all data your payment provider requires
        in future steps is present.
        """
        raise NotImplementedError()  # NOQA

    def execute_payment(self, request: HttpRequest, payment: OrderPayment) -> str:
        """
        After the user has confirmed their purchase, this method will be called to complete
        the payment process. This is the place to actually move the money if applicable.
        You will be passed an :py:class:`pretix.base.models.OrderPayment` object that contains
        the amount of money that should be paid.

        If you need any special behavior, you can return a string
        containing the URL the user will be redirected to. If you are done with your process
        you should return the user to the order's detail page.

        If the payment is completed, you should call ``payment.confirm()``. Please note that this might
        raise a ``Quota.QuotaExceededException`` if (and only if) the payment term of this order is over and
        some of the items are sold out. You should use the exception message to display a meaningful error
        to the user.

        The default implementation just returns ``None`` and therefore leaves the
        order unpaid. The user will be redirected to the order's detail page by default.

        On errors, you should raise a ``PaymentException``.

        :param order: The order object
        :param payment: An ``OrderPayment`` instance
        """
        return None

    def order_pending_mail_render(self, order: Order, payment: OrderPayment) -> str:
        """
        After the user has submitted their order, they will receive a confirmation
        email. You can return a string from this method if you want to add additional
        information to this email.

        :param order: The order object
        :param payment: The payment object
        """
        return ""

    def order_change_allowed(self, order: Order) -> bool:
        """
        Will be called to check whether it is allowed to change the payment method of
        an order to this one.

        The default implementation checks for the _availability_date setting to be either unset or in the future,
        as well as for the _total_max, _total_min and _restricted_countries settings.

        :param order: The order object
        """
        ps = order.pending_sum
        if self.settings._total_max is not None and ps > Decimal(self.settings._total_max):
            return False

        if self.settings._total_min is not None and ps < Decimal(self.settings._total_min):
            return False

        if self.settings.get('_hidden', as_type=bool):
            return False

        restricted_countries = self.settings.get('_restricted_countries', as_type=list)
        if restricted_countries:
            try:
                ia = order.invoice_address
            except InvoiceAddress.DoesNotExist:
                return True
            else:
                if str(ia.country) not in restricted_countries:
                    return False

        if order.sales_channel not in self.settings.get('_restrict_to_sales_channels', as_type=list, default=['web']):
            return False

        return self._is_still_available(order=order)

    def payment_prepare(self, request: HttpRequest, payment: OrderPayment) -> Union[bool, str]:
        """
        Will be called if the user retries to pay an unpaid order (after the user filled in
        e.g. the form returned by :py:meth:`payment_form`) or if the user changes the payment
        method.

        It should return and report errors the same way as :py:meth:`checkout_prepare`, but
        receives an ``Order`` object instead of a cart object.

        Note: The ``Order`` object given to this method might be different from the version
        stored in the database as it's total will already contain the payment fee for the
        new payment method.
        """
        form = self.payment_form(request)
        if form.is_valid():
            for k, v in form.cleaned_data.items():
                request.session['payment_%s_%s' % (self.identifier, k)] = v
            return True
        else:
            return False

    def payment_control_render(self, request: HttpRequest, payment: OrderPayment) -> str:
        """
        Will be called if the *event administrator* views the details of a payment.

        It should return HTML code containing information regarding the current payment
        status and, if applicable, next steps.

        The default implementation returns the verbose name of the payment provider.

        :param order: The order object
        """
        return ''

    def refund_control_render(self, request: HttpRequest, refund: OrderRefund) -> str:
        """
        Will be called if the *event administrator* views the details of a refund.

        It should return HTML code containing information regarding the current refund
        status and, if applicable, next steps.

        The default implementation returns an empty string.

        :param order: The order object
        """
        return ''

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        """
        Will be called to check if the provider supports automatic refunding for this
        payment.
        """
        return False

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        """
        Will be called to check if the provider supports automatic partial refunding for this
        payment.
        """
        return False

    def cancel_payment(self, payment: OrderPayment):
        """
        Will be called to cancel a payment. The default implementation just sets the payment state to canceled,
        but in some cases you might want to notify an external provider.

        On success, you should set ``payment.state = OrderPayment.PAYMENT_STATE_CANCELED`` (or call the super method).
        On failure, you should raise a PaymentException.
        """
        payment.state = OrderPayment.PAYMENT_STATE_CANCELED
        payment.save(update_fields=['state'])

    def execute_refund(self, refund: OrderRefund):
        """
        Will be called to execute an refund. Note that refunds have an amount property and can be partial.

        This should transfer the money back (if possible).
        On success, you should call ``refund.done()``.
        On failure, you should raise a PaymentException.
        """
        raise PaymentException(_('Automatic refunds are not supported by this payment provider.'))

    def shred_payment_info(self, obj: Union[OrderPayment, OrderRefund]):
        """
        When personal data is removed from an event, this method is called to scrub payment-related data
        from a payment or refund. By default, it removes all info from the ``info`` attribute. You can override
        this behavior if you want to retain attributes that are not personal data on their own, i.e. a
        reference to a transaction in an external system. You can also override this to scrub more data, e.g.
        data from external sources that is saved in LogEntry objects or other places.

        :param order: An order
        """
        obj.info = '{}'
        obj.save(update_fields=['info'])

    def api_payment_details(self, payment: OrderPayment):
        """
        Will be called to populate the ``details`` parameter of the payment in the REST API.

        :param payment: The payment in question.
        :return: A serializable dictionary
        """
        return {}

    def matching_id(self, payment: OrderPayment):
        """
        Will be called to get an ID for a matching this payment when comparing pretix records with records of an external
        source. This should return the main transaction ID for your API.

        :param payment: The payment in question.
        :return: A string or None
        """
        return None


class PaymentException(Exception):
    pass


class FreeOrderProvider(BasePaymentProvider):
    is_implicit = True
    is_enabled = True
    identifier = "free"

    def checkout_confirm_render(self, request: HttpRequest) -> str:
        return _("No payment is required as this order only includes products which are free of charge.")

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        return True

    @property
    def verbose_name(self) -> str:
        return _("Free of charge")

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            payment.confirm(send_mail=False)
        except Quota.QuotaExceededException as e:
            raise PaymentException(str(e))

    @property
    def settings_form_fields(self) -> dict:
        return {}

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        from .services.cart import get_fees

        cart = get_cart(request)
        total = get_cart_total(request)
        total += sum([f.value for f in get_fees(self.event, request, total, None, None, cart)])
        return total == 0

    def order_change_allowed(self, order: Order) -> bool:
        return False


class BoxOfficeProvider(BasePaymentProvider):
    is_implicit = True
    is_enabled = True
    identifier = "boxoffice"
    verbose_name = _("Box office")

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            payment.confirm(send_mail=False)
        except Quota.QuotaExceededException as e:
            raise PaymentException(str(e))

    @property
    def settings_form_fields(self) -> dict:
        return {}

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        return False

    def order_change_allowed(self, order: Order) -> bool:
        return False

    def api_payment_details(self, payment: OrderPayment):
        return {
            "pos_id": payment.info_data.get('pos_id', None),
            "receipt_id": payment.info_data.get('receipt_id', None),
        }

    def payment_control_render(self, request, payment) -> str:
        if not payment.info:
            return
        payment_info = json.loads(payment.info)
        template = get_template('pretixcontrol/boxoffice/payment.html')

        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'payment_info': payment_info,
            'payment': payment,
            'provider': self,
        }
        return template.render(ctx)


class ManualPayment(BasePaymentProvider):
    identifier = 'manual'
    verbose_name = _('Manual payment')

    @property
    def test_mode_message(self):
        return _('In test mode, you can just manually mark this order as paid in the backend after it has been '
                 'created.')

    def is_implicit(self, request: HttpRequest):
        return 'pretix.plugins.manualpayment' not in self.event.plugins

    def is_allowed(self, request: HttpRequest, total: Decimal=None):
        return 'pretix.plugins.manualpayment' in self.event.plugins and super().is_allowed(request, total)

    def order_change_allowed(self, order: Order):
        return 'pretix.plugins.manualpayment' in self.event.plugins and super().order_change_allowed(order)

    @property
    def public_name(self):
        return str(self.settings.get('public_name', as_type=LazyI18nString))

    @property
    def settings_form_fields(self):
        d = OrderedDict(
            [
                ('public_name', I18nFormField(
                    label=_('Payment method name'),
                    widget=I18nTextInput,
                )),
                ('checkout_description', I18nFormField(
                    label=_('Payment process description during checkout'),
                    help_text=_('This text will be shown during checkout when the user selects this payment method. '
                                'It should give a short explanation on this payment method.'),
                    widget=I18nTextarea,
                )),
                ('email_instructions', I18nFormField(
                    label=_('Payment process description in order confirmation emails'),
                    help_text=_('This text will be included for the {payment_info} placeholder in order confirmation '
                                'mails. It should instruct the user on how to proceed with the payment. You can use'
                                'the placeholders {order}, {total}, {currency} and {total_with_currency}'),
                    widget=I18nTextarea,
                    validators=[PlaceholderValidator(['{order}', '{total}', '{currency}', '{total_with_currency}'])],
                )),
                ('pending_description', I18nFormField(
                    label=_('Payment process description for pending orders'),
                    help_text=_('This text will be shown on the order confirmation page for pending orders. '
                                'It should instruct the user on how to proceed with the payment. You can use'
                                'the placeholders {order}, {total}, {currency} and {total_with_currency}'),
                    widget=I18nTextarea,
                    validators=[PlaceholderValidator(['{order}', '{total}', '{currency}', '{total_with_currency}'])],
                )),
            ] + list(super().settings_form_fields.items())
        )
        d.move_to_end('_enabled', last=False)
        return d

    def payment_form_render(self, request) -> str:
        return rich_text(
            str(self.settings.get('checkout_description', as_type=LazyI18nString))
        )

    def checkout_prepare(self, request, total):
        return True

    def payment_is_valid_session(self, request):
        return True

    def checkout_confirm_render(self, request):
        return self.payment_form_render(request)

    def format_map(self, order):
        return {
            'order': order.code,
            'total': order.total,
            'currency': self.event.currency,
            'total_with_currency': money_filter(order.total, self.event.currency)
        }

    def order_pending_mail_render(self, order) -> str:
        msg = str(self.settings.get('email_instructions', as_type=LazyI18nString)).format_map(self.format_map(order))
        return msg

    def payment_pending_render(self, request, payment) -> str:
        return rich_text(
            str(self.settings.get('pending_description', as_type=LazyI18nString)).format_map(self.format_map(payment.order))
        )


class OffsettingProvider(BasePaymentProvider):
    is_enabled = True
    identifier = "offsetting"
    verbose_name = _("Offsetting")
    is_implicit = True

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            payment.confirm()
        except Quota.QuotaExceededException as e:
            raise PaymentException(str(e))

    def execute_refund(self, refund: OrderRefund):
        code = refund.info_data['orders'][0]
        try:
            order = Order.objects.get(code=code, event__organizer=self.event.organizer)
        except Order.DoesNotExist:
            raise PaymentException(_('You entered an order that could not be found.'))
        p = order.payments.create(
            state=OrderPayment.PAYMENT_STATE_PENDING,
            amount=refund.amount,
            payment_date=now(),
            provider='offsetting',
            info=json.dumps({'orders': [refund.order.code]})
        )
        try:
            p.confirm(ignore_date=True)
        except Quota.QuotaExceededException:
            pass

    @property
    def settings_form_fields(self) -> dict:
        return {}

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        return False

    def order_change_allowed(self, order: Order) -> bool:
        return False

    def api_payment_details(self, payment: OrderPayment):
        return {
            "orders": payment.info_data.get('orders', []),
        }

    def payment_control_render(self, request: HttpRequest, payment: OrderPayment) -> str:
        return _('Balanced against orders: %s' % ', '.join(payment.info_data['orders']))


class GiftCardPayment(BasePaymentProvider):
    identifier = "giftcard"
    verbose_name = _("Gift card")
    priority = 10

    @property
    def settings_form_fields(self):
        f = super().settings_form_fields
        del f['_fee_abs']
        del f['_fee_percent']
        del f['_fee_reverse_calc']
        del f['_total_min']
        del f['_total_max']
        del f['_invoice_text']
        return f

    @property
    def test_mode_message(self) -> str:
        return _("In test mode, only test cards will work.")

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
        return super().is_allowed(request, total) and self.event.organizer.has_gift_cards

    def order_change_allowed(self, order: Order) -> bool:
        return super().order_change_allowed(order) and self.event.organizer.has_gift_cards

    def payment_form_render(self, request: HttpRequest, total: Decimal) -> str:
        return get_template('pretixcontrol/giftcards/checkout.html').render({})

    def checkout_confirm_render(self, request) -> str:
        return get_template('pretixcontrol/giftcards/checkout_confirm.html').render({})

    def refund_control_render(self, request, refund) -> str:
        from .models import GiftCard

        if 'gift_card' in refund.info_data:
            gc = GiftCard.objects.get(pk=refund.info_data.get('gift_card'))
            template = get_template('pretixcontrol/giftcards/payment.html')

            ctx = {
                'request': request,
                'event': self.event,
                'gc': gc,
            }
            return template.render(ctx)

    def payment_control_render(self, request, payment) -> str:
        from .models import GiftCard

        if 'gift_card' in payment.info_data:
            gc = GiftCard.objects.get(pk=payment.info_data.get('gift_card'))
            template = get_template('pretixcontrol/giftcards/payment.html')

            ctx = {
                'request': request,
                'event': self.event,
                'gc': gc,
            }
            return template.render(ctx)

    def api_payment_details(self, payment: OrderPayment):
        from .models import GiftCard
        gc = GiftCard.objects.get(pk=payment.info_data.get('gift_card'))
        return {
            'gift_card': {
                'id': gc.pk,
                'secret': gc.secret,
                'organizer': gc.issuer.slug
            }
        }

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return True

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        return True

    def checkout_prepare(self, request: HttpRequest, cart: Dict[str, Any]) -> Union[bool, str, None]:
        for p in get_cart(request):
            if p.item.issue_giftcard:
                messages.error(request, _("You cannot pay with gift cards when buying a gift card."))
                return

        cs = cart_session(request)
        try:
            gc = self.event.organizer.accepted_gift_cards.get(
                secret=request.POST.get("giftcard")
            )
            if gc.currency != self.event.currency:
                messages.error(request, _("This gift card does not support this currency."))
                return
            if gc.testmode and not self.event.testmode:
                messages.error(request, _("This gift card can only be used in test mode."))
                return
            if not gc.testmode and self.event.testmode:
                messages.error(request, _("Only test gift cards can be used in test mode."))
                return
            if gc.value <= Decimal("0.00"):
                messages.error(request, _("All credit on this gift card has been used."))
                return
            if 'gift_cards' not in cs:
                cs['gift_cards'] = []
            elif gc.pk in cs['gift_cards']:
                messages.error(request, _("This gift card is already used for your payment."))
                return
            cs['gift_cards'] = cs['gift_cards'] + [gc.pk]

            remainder = cart['total'] - gc.value
            if remainder >= Decimal('0.00'):
                del cs['payment']
                messages.success(request, _("Your gift card has been applied, but {} still need to be paid. Please select a payment method.").format(
                    money_filter(remainder, self.event.currency)
                ))
            else:
                messages.success(request, _("Your gift card has been applied."))

            kwargs = {'step': 'payment'}
            if request.resolver_match and 'cart_namespace' in request.resolver_match.kwargs:
                kwargs['cart_namespace'] = request.resolver_match.kwargs['cart_namespace']
            return eventreverse(self.event, 'presale:event.checkout', kwargs=kwargs)
        except GiftCard.DoesNotExist:
            if self.event.vouchers.filter(code__iexact=request.POST.get("giftcard")).exists():
                messages.warning(request, _("You entered a voucher instead of a gift card. Vouchers can only be entered on the first page of the shop below "
                                            "the product selection."))
            else:
                messages.error(request, _("This gift card is not known."))
        except GiftCard.MultipleObjectsReturned:
            messages.error(request, _("This gift card can not be redeemed since its code is not unique. Please contact the organizer of this event."))

    def payment_prepare(self, request: HttpRequest, payment: OrderPayment) -> Union[bool, str, None]:
        for p in payment.order.positions.all():
            if p.item.issue_giftcard:
                messages.error(request, _("You cannot pay with gift cards when buying a gift card."))
                return

        try:
            gc = self.event.organizer.accepted_gift_cards.get(
                secret=request.POST.get("giftcard")
            )
            if gc.currency != self.event.currency:
                messages.error(request, _("This gift card does not support this currency."))
                return
            if gc.testmode and not payment.order.testmode:
                messages.error(request, _("This gift card can only be used in test mode."))
                return
            if not gc.testmode and payment.order.testmode:
                messages.error(request, _("Only test gift cards can be used in test mode."))
                return
            if gc.value <= Decimal("0.00"):
                messages.error(request, _("All credit on this gift card has been used."))
                return
            payment.info_data = {
                'gift_card': gc.pk,
                'retry': True
            }
            payment.amount = min(payment.amount, gc.value)
            payment.save()

            return True
        except GiftCard.DoesNotExist:
            if self.event.vouchers.filter(code__iexact=request.POST.get("giftcard")).exists():
                messages.warning(request, _("You entered a voucher instead of a gift card. Vouchers can only be entered on the first page of the shop below "
                                            "the product selection."))
            else:
                messages.error(request, _("This gift card is not known."))
        except GiftCard.MultipleObjectsReturned:
            messages.error(request, _("This gift card can not be redeemed since its code is not unique. Please contact the organizer of this event."))

    def execute_payment(self, request: HttpRequest, payment: OrderPayment) -> str:
        # This method will only be called when retrying payments, e.g. after a payment_prepare call. It is not called
        # during the order creation phase because this payment provider is a special case.
        for p in payment.order.positions.all():  # noqa - just a safeguard
            if p.item.issue_giftcard:
                raise PaymentException(_("You cannot pay with gift cards when buying a gift card."))

        gcpk = payment.info_data.get('gift_card')
        if not gcpk or not payment.info_data.get('retry'):
            raise PaymentException("Invalid state, should never occur.")
        with transaction.atomic():
            gc = GiftCard.objects.select_for_update().get(pk=gcpk)
            if gc.currency != self.event.currency:  # noqa - just a safeguard
                raise PaymentException(_("This gift card does not support this currency."))
            if not gc.accepted_by(self.event.organizer):  # noqa - just a safeguard
                raise PaymentException(_("This gift card is not accepted by this event organizer."))
            if payment.amount > gc.value:  # noqa - just a safeguard
                raise PaymentException(_("This gift card was used in the meantime. Please try again"))
            trans = gc.transactions.create(
                value=-1 * payment.amount,
                order=payment.order,
                payment=payment
            )
            payment.info_data = {
                'gift_card': gc.pk,
                'transaction_id': trans.pk,
            }
            payment.confirm()

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        return True

    @transaction.atomic()
    def execute_refund(self, refund: OrderRefund):
        from .models import GiftCard
        gc = GiftCard.objects.get(pk=refund.info_data.get('gift_card') or refund.payment.info_data.get('gift_card'))
        trans = gc.transactions.create(
            value=refund.amount,
            order=refund.order,
            refund=refund
        )
        refund.info_data = {
            'gift_card': gc.pk,
            'transaction_id': trans.pk,
        }
        refund.done()


@receiver(register_payment_providers, dispatch_uid="payment_free")
def register_payment_provider(sender, **kwargs):
    return [FreeOrderProvider, BoxOfficeProvider, OffsettingProvider, ManualPayment, GiftCardPayment]
