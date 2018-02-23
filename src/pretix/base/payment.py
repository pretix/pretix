import logging
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Union

import pytz
from django import forms
from django.conf import settings
from django.contrib import messages
from django.dispatch import receiver
from django.forms import Form
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea
from i18nfield.strings import LazyI18nString

from pretix.base.models import CartPosition, Event, Order, Quota
from pretix.base.reldate import RelativeDateField, RelativeDateWrapper
from pretix.base.settings import SettingsSandbox
from pretix.base.signals import register_payment_providers
from pretix.helpers.money import DecimalTextInput
from pretix.presale.views import get_cart_total
from pretix.presale.views.cart import get_or_create_cart_id

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

    @property
    def is_implicit(self) -> bool:
        """
        Returns whether or whether not this payment provider is an "implicit" payment provider that will
        *always* and unconditionally be used if is_allowed() returns True and does not require any input.
        This is  intended to be used by the FreePaymentProvider, which skips the payment choice page.
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
    def is_enabled(self) -> bool:
        """
        Returns whether or whether not this payment provider is enabled.
        By default, this is determined by the value of the ``_enabled`` setting.
        """
        return self.settings.get('_enabled', as_type=bool)

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
        return OrderedDict([
            ('_enabled',
             forms.BooleanField(
                 label=_('Enable payment method'),
                 required=False,
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
                 help_text=_('Percentage of the order total. Note that this percentage will currently only '
                             'be calculated on the summed price of sold tickets, not on other fees like e.g. shipping '
                             'fees, if there are any.'),
                 localize=True,
                 required=False,
             )),
            ('_availability_date',
             RelativeDateField(
                 label=_('Available until'),
                 help_text=_('Users will not be able to choose this payment provider after the given date.'),
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
        ])

    def settings_content_render(self, request: HttpRequest) -> str:
        """
        When the event's administrator visits the event configuration
        page, this method is called. It may return HTML containing additional information
        that is displayed below the form fields configured in ``settings_form_fields``.
        """
        pass

    def render_invoice_text(self, order: Order) -> str:
        """
        This is called when an invoice for an order with this payment provider is generated.
        The default implementation returns the content of the _invoice_text configuration
        variable (an I18nString), or an empty string if unconfigured.
        """
        if order.status == Order.STATUS_PAID:
            return pgettext_lazy('invoice', 'The payment for this invoice has already been received.')
        return self.settings.get('_invoice_text', as_type=LazyI18nString, default='')

    @property
    def payment_form_fields(self) -> dict:
        """
        This is used by the default implementation of :py:meth:`checkout_form`.
        It should return an object similar to :py:attr:`settings_form_fields`.

        The default implementation returns an empty dictionary.
        """
        return {}

    def payment_form(self, request: HttpRequest) -> Form:
        """
        This is called by the default implementation of :py:meth:`checkout_form_render`
        to obtain the form that is displayed to the user during the checkout
        process. The default implementation constructs the form using
        :py:attr:`checkout_form_fields` and sets appropriate prefixes for the form
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

    def is_allowed(self, request: HttpRequest) -> bool:
        """
        You can use this method to disable this payment provider for certain groups
        of users, products or other criteria. If this method returns ``False``, the
        user will not be able to select this payment method. This will only be called
        during checkout, not on retrying.

        The default implementation checks for the _availability_date setting to be either unset or in the future.
        """
        return self._is_still_available(cart_id=get_or_create_cart_id(request))

    def payment_form_render(self, request: HttpRequest) -> str:
        """
        When the user selects this provider as his preferred payment method,
        they will be shown the HTML you return from this method.

        The default implementation will call :py:meth:`checkout_form`
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
        If the user has successfully filled in his payment data, they will be redirected
        to a confirmation page which lists all details of his order for a final review.
        This method should return the HTML which should be displayed inside the
        'Payment' box on this page.

        In most cases, this should include a short summary of the user's input and
        a short explanation on how the payment process will continue.
        """
        raise NotImplementedError()  # NOQA

    def checkout_prepare(self, request: HttpRequest, cart: Dict[str, Any]) -> Union[bool, str]:
        """
        Will be called after the user selects this provider as his payment method.
        If you provided a form to the user to enter payment data, this method should
        at least store the user's input into his session.

        This method should return ``False`` if the user's input was invalid, ``True``
        if the input was valid and the frontend should continue with default behavior
        or a string containing a URL if the user should be redirected somewhere else.

        On errors, you should use Django's message framework to display an error message
        to the user (or the normal form validation error messages).

        The default implementation stores the input into the form returned by
        :py:meth:`payment_form` in the user's session.

        If your payment method requires you to redirect the user to an external provider,
        this might be the place to do so.

        .. IMPORTANT:: If this is called, the user has not yet confirmed his or her order.
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

    def payment_perform(self, request: HttpRequest, order: Order) -> str:
        """
        After the user has confirmed their purchase, this method will be called to complete
        the payment process. This is the place to actually move the money if applicable.
        If you need any special  behavior,  you can return a string
        containing the URL the user will be redirected to. If you are done with your process
        you should return the user to the order's detail page.

        If the payment is completed, you should call ``pretix.base.services.orders.mark_order_paid(order, provider, info)``
        with ``provider`` being your :py:attr:`identifier` and ``info`` being any string
        you might want to store for later usage. Please note that ``mark_order_paid`` might
        raise a ``Quota.QuotaExceededException`` if (and only if) the payment term of this
        order is over and some of the items are sold out. You should use the exception message
        to display a meaningful error to the user.

        The default implementation just returns ``None`` and therefore leaves the
        order unpaid. The user will be redirected to the order's detail page by default.

        On errors, you should raise a ``PaymentException``.
        :param order: The order object
        """
        return None

    def order_pending_mail_render(self, order: Order) -> str:
        """
        After the user has submitted their order, they will receive a confirmation
        email. You can return a string from this method if you want to add additional
        information to this email.

        :param order: The order object
        """
        return ""

    def order_pending_render(self, request: HttpRequest, order: Order) -> str:
        """
        If the user visits a detail page of an order which has not yet been paid but
        this payment method was selected during checkout, this method will be called
        to provide HTML content for the 'payment' box on the page.

        It should contain instructions on how to continue with the payment process,
        either in form of text or buttons/links/etc.

        :param order: The order object
        """
        raise NotImplementedError()  # NOQA

    def order_change_allowed(self, order: Order) -> bool:
        """
        Will be called to check whether it is allowed to change the payment method of
        an order to this one.

        The default implementation checks for the _availability_date setting to be either unset or in the future.

        :param order: The order object
        """
        return self._is_still_available(order=order)

    def order_can_retry(self, order: Order) -> bool:
        """
        Will be called if the user views the detail page of an unpaid order to determine
        whether the user should be presented with an option to retry the payment. The default
        implementation always returns False.

        If you want to enable retrials for your payment method, the best is to just return
        ``self._is_still_available()`` from this method to disable it as soon as the method
        gets disabled or the methods end date is reached.

        The retry workflow is also used if a user switches to this payment method for an existing
        order!

        :param order: The order object
        """
        return False

    def retry_prepare(self, request: HttpRequest, order: Order) -> Union[bool, str]:
        """
        Deprecated, use order_prepare instead
        """
        raise DeprecationWarning('retry_prepare is deprecated, use order_prepare instead')
        return self.order_prepare(request, order)

    def order_prepare(self, request: HttpRequest, order: Order) -> Union[bool, str]:
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

    def order_paid_render(self, request: HttpRequest, order: Order) -> str:
        """
        Will be called if the user views the detail page of a paid order which is
        associated with this payment provider.

        It should return HTML code which should be displayed to the user or None,
        if there is nothing to say (like the default implementation does).

        :param order: The order object
        """
        return None

    def order_control_render(self, request: HttpRequest, order: Order) -> str:
        """
        Will be called if the *event administrator* views the detail page of an order
        which is associated with this payment provider.

        It should return HTML code containing information regarding the current payment
        status and, if applicable, next steps.

        The default implementation returns the verbose name of the payment provider.

        :param order: The order object
        """
        return _('Payment provider: %s' % self.verbose_name)

    def order_control_refund_render(self, order: Order, request: HttpRequest=None) -> str:
        """
        Will be called if the event administrator clicks an order's 'refund' button.
        This can be used to display information *before* the order is being refunded.

        It should return HTML code which should be displayed to the user. It should
        contain information about to which extend the money will be refunded
        automatically.

        :param order: The order object
        :param request: The HTTP request

        .. versionchanged:: 1.6

           The parameter ``request`` has been added.
        """
        return '<div class="alert alert-warning">%s</div>' % _('The money can not be automatically refunded, '
                                                               'please transfer the money back manually.')

    def order_control_refund_perform(self, request: HttpRequest, order: Order) -> Union[bool, str]:
        """
        Will be called if the event administrator confirms the refund.

        This should transfer the money back (if possible). You can return the URL the
        user should be redirected to if you need special behavior or None to continue
        with default behavior.

        On failure, you should use Django's message framework to display an error message
        to the user.

        The default implementation sets the Order's state to refunded and shows a success
        message.

        :param request: The HTTP request
        :param order: The order object
        """
        from pretix.base.services.orders import mark_order_refunded

        mark_order_refunded(order, user=request.user)
        messages.success(request, _('The order has been marked as refunded. Please transfer the money '
                                    'back to the buyer manually.'))


class PaymentException(Exception):
    pass


class FreeOrderProvider(BasePaymentProvider):

    @property
    def is_implicit(self) -> bool:
        return True

    @property
    def is_enabled(self) -> bool:
        return True

    @property
    def identifier(self) -> str:
        return "free"

    def checkout_confirm_render(self, request: HttpRequest) -> str:
        return _("No payment is required as this order only includes products which are free of charge.")

    def order_pending_render(self, request: HttpRequest, order: Order) -> str:
        pass

    def payment_is_valid_session(self, request: HttpRequest) -> bool:
        return True

    @property
    def verbose_name(self) -> str:
        return _("Free of charge")

    def payment_perform(self, request: HttpRequest, order: Order):
        from pretix.base.services.orders import mark_order_paid
        try:
            mark_order_paid(order, 'free', send_mail=False)
        except Quota.QuotaExceededException as e:
            raise PaymentException(str(e))

    @property
    def settings_form_fields(self) -> dict:
        return {}

    def order_control_refund_render(self, order: Order) -> str:
        return ''

    def order_control_refund_perform(self, request: HttpRequest, order: Order) -> Union[bool, str]:
        """
        Will be called if the event administrator confirms the refund.

        This should transfer the money back (if possible). You can return the URL the
        user should be redirected to if you need special behavior or None to continue
        with default behavior.

        On failure, you should use Django's message framework to display an error message
        to the user.

        The default implementation sets the Order's state to refunded and shows a success
        message.

        :param request: The HTTP request
        :param order: The order object
        """
        from pretix.base.services.orders import mark_order_refunded

        mark_order_refunded(order, user=request.user)
        messages.success(request, _('The order has been marked as refunded.'))

    def is_allowed(self, request: HttpRequest) -> bool:
        from .services.cart import get_fees

        total = get_cart_total(request)
        total += sum([f.value for f in get_fees(self.event, request, total, None, None)])
        return total == 0

    def order_change_allowed(self, order: Order) -> bool:
        return False


@receiver(register_payment_providers, dispatch_uid="payment_free")
def register_payment_provider(sender, **kwargs):
    return FreeOrderProvider
