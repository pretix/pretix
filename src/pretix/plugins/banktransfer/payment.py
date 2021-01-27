import json
import textwrap
from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.translation import gettext, gettext_lazy as _
from i18nfield.fields import I18nFormField, I18nTextarea
from i18nfield.forms import I18nTextInput
from i18nfield.strings import LazyI18nString
from localflavor.generic.forms import BICFormField, IBANFormField
from localflavor.generic.validators import IBANValidator

from pretix.base.models import Order, OrderPayment, OrderRefund
from pretix.base.payment import BasePaymentProvider


class BankTransfer(BasePaymentProvider):
    identifier = 'banktransfer'
    verbose_name = _('Bank transfer')
    abort_pending_allowed = True

    @staticmethod
    def form_fields():
        return OrderedDict([
            ('ack',
             forms.BooleanField(
                 label=_('I have understood that people will pay the ticket price directly to my bank account and '
                         'pretix cannot automatically know what payments arrived. Therefore, I will either mark '
                         'payments as complete manually, or regularly import a digital bank statement in order to '
                         'give pretix the required information.'),
                 required=True,
             )),
            ('bank_details_type', forms.ChoiceField(
                label=_('Bank account type'),
                widget=forms.RadioSelect,
                choices=(
                    ('sepa', _('SEPA bank account')),
                    ('other', _('Other bank account')),
                ),
                initial='sepa'
            )),
            ('bank_details_sepa_name', forms.CharField(
                label=_('Name of account holder'),
                widget=forms.TextInput(
                    attrs={
                        'data-display-dependency': '#id_payment_banktransfer_bank_details_type_0',
                        'data-required-if': '#id_payment_banktransfer_bank_details_type_0'
                    }
                ),
                required=False
            )),
            ('bank_details_sepa_iban', IBANFormField(
                label=_('IBAN'),
                required=False,
                widget=forms.TextInput(
                    attrs={
                        'data-display-dependency': '#id_payment_banktransfer_bank_details_type_0',
                        'data-required-if': '#id_payment_banktransfer_bank_details_type_0'
                    }
                ),
            )),
            ('bank_details_sepa_bic', BICFormField(
                label=_('BIC'),
                widget=forms.TextInput(
                    attrs={
                        'data-display-dependency': '#id_payment_banktransfer_bank_details_type_0',
                        'data-required-if': '#id_payment_banktransfer_bank_details_type_0'
                    }
                ),
                required=False
            )),
            ('bank_details_sepa_bank', forms.CharField(
                label=_('Name of bank'),
                widget=forms.TextInput(
                    attrs={
                        'data-display-dependency': '#id_payment_banktransfer_bank_details_type_0',
                        'data-required-if': '#id_payment_banktransfer_bank_details_type_0'
                    }
                ),
                required=False
            )),
            ('bank_details', I18nFormField(
                label=_('Bank account details'),
                widget=I18nTextarea,
                help_text=_(
                    'Include everything else that your customers might need to send you a bank transfer payment. '
                    'If you have lots of international customers, they might need your full address and your '
                    'bank\'s full address.'),
                widget_kwargs={'attrs': {
                    'rows': '4',
                    'placeholder': _(
                        'For SEPA accounts, you can leave this empty. Otherwise, please add everything that '
                        'your customers need to transfer the money, e.g. account numbers, routing numbers, '
                        'addresses, etc.'
                    ),
                }},
                required=False
            )),
            ('invoice_immediately',
             forms.BooleanField(
                 label=_('Create an invoice for orders using bank transfer immediately if the event is otherwise '
                         'configured to create invoices after payment is completed.'),
                 required=False,
             )),
            ('public_name', I18nFormField(
                label=_('Payment method name'),
                widget=I18nTextInput,
                required=False
            )),
            ('omit_hyphen', forms.BooleanField(
                label=_('Do not include hyphens in the payment reference.'),
                help_text=_('This is required in some countries.'),
                required=False
            )),
            ('include_invoice_number', forms.BooleanField(
                label=_('Include invoice number in the payment reference.'),
                required=False
            )),
            ('prefix', forms.CharField(
                label=_('Prefix for the payment reference'),
                required=False,
            )),
            ('pending_description', I18nFormField(
                label=_('Additional text to show on pending orders'),
                help_text=_('This text will be shown on the order confirmation page for pending orders in addition to '
                            'the standard text.'),
                widget=I18nTextarea,
                required=False,
            )),
        ])

    @property
    def public_name(self):
        return str(self.settings.get('public_name', as_type=LazyI18nString) or self.verbose_name)

    @property
    def test_mode_message(self):
        return _('In test mode, you can just manually mark this order as paid in the backend after it has been '
                 'created.')

    @property
    def requires_invoice_immediately(self):
        return self.settings.get('invoice_immediately', False, as_type=bool)

    @property
    def settings_form_fields(self):
        d = OrderedDict(list(super().settings_form_fields.items()) + list(BankTransfer.form_fields().items()))
        d.move_to_end('bank_details', last=False)
        d.move_to_end('bank_details_sepa_bank', last=False)
        d.move_to_end('bank_details_sepa_bic', last=False)
        d.move_to_end('bank_details_sepa_iban', last=False)
        d.move_to_end('bank_details_sepa_name', last=False)
        d.move_to_end('bank_details_type', last=False)
        d.move_to_end('ack', last=False)
        d.move_to_end('_enabled', last=False)
        return d

    def settings_form_clean(self, cleaned_data):
        if cleaned_data.get('payment_banktransfer_bank_details_type') == 'sepa':
            for f in ('bank_details_sepa_name', 'bank_details_sepa_bank', 'bank_details_sepa_bic', 'bank_details_sepa_iban'):
                if not cleaned_data.get('payment_banktransfer_%s' % f):
                    raise ValidationError(
                        {'payment_banktransfer_%s' % f: _('Please fill out your bank account details.')})
        else:
            if not cleaned_data.get('payment_banktransfer_bank_details'):
                raise ValidationError(
                    {'payment_banktransfer_bank_details': _('Please enter your bank account details.')})
        return cleaned_data

    def payment_form_render(self, request, total=None, order=None) -> str:
        template = get_template('pretixplugins/banktransfer/checkout_payment_form.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'code': self._code(order) if order else None,
            'details': self.settings.get('bank_details', as_type=LazyI18nString),
        }
        return template.render(ctx)

    def checkout_prepare(self, request, total):
        return True

    def payment_prepare(self, request: HttpRequest, payment: OrderPayment):
        return True

    def payment_is_valid_session(self, request):
        return True

    def checkout_confirm_render(self, request, order=None):
        return self.payment_form_render(request, order=order)

    def order_pending_mail_render(self, order, payment) -> str:
        template = get_template('pretixplugins/banktransfer/email/order_pending.txt')
        bankdetails = []
        if self.settings.get('bank_details_type') == 'sepa':
            bankdetails += [
                _("Account holder"), ": ", self.settings.get('bank_details_sepa_name'), "\n",
                _("IBAN"), ": ", self.settings.get('bank_details_sepa_iban'), "\n",
                _("BIC"), ": ", self.settings.get('bank_details_sepa_bic'), "\n",
                _("Bank"), ": ", self.settings.get('bank_details_sepa_bank'),
            ]
        if bankdetails and self.settings.get('bank_details', as_type=LazyI18nString):
            bankdetails.append("\n")
        bankdetails.append(self.settings.get('bank_details', as_type=LazyI18nString))
        ctx = {
            'event': self.event,
            'order': order,
            'code': self._code(order),
            'amount': payment.amount,
            'details': textwrap.indent(''.join(str(i) for i in bankdetails), '    '),
        }
        return template.render(ctx)

    def payment_pending_render(self, request: HttpRequest, payment: OrderPayment):
        template = get_template('pretixplugins/banktransfer/pending.html')
        ctx = {
            'event': self.event,
            'code': self._code(payment.order),
            'order': payment.order,
            'amount': payment.amount,
            'settings': self.settings,
            'pending_description': self.settings.get('pending_description', as_type=LazyI18nString),
            'details': self.settings.get('bank_details', as_type=LazyI18nString),
        }
        return template.render(ctx)

    def payment_control_render(self, request: HttpRequest, payment: OrderPayment) -> str:
        warning = None
        if not self.payment_refund_supported(payment):
            warning = _("Invalid IBAN/BIC")
        return self._render_control_info(request, payment.order, payment.info_data, warning=warning)

    def _render_control_info(self, request, order, info_data, **extra_context):
        template = get_template('pretixplugins/banktransfer/control.html')
        ctx = {'request': request, 'event': self.event,
               'code': self._code(order),
               'payment_info': info_data, 'order': order,
               **extra_context}
        return template.render(ctx)

    def _code(self, order):
        prefix = self.settings.get('prefix', default='')
        li = order.invoices.last()
        invoice_number = li.number if self.settings.get('include_invoice_number', as_type=bool) and li else ''

        code = " ".join((prefix, order.full_code, invoice_number)).strip(" ")

        if self.settings.get('omit_hyphen', as_type=bool):
            code = code.replace('-', '')

        return code

    def shred_payment_info(self, obj):
        if not obj.info_data:
            return
        d = obj.info_data
        d['reference'] = '█'
        d['payer'] = '█'
        d['_shredded'] = True
        obj.info = json.dumps(d)
        obj.save(update_fields=['info'])

    @staticmethod
    def norm(s):
        return s.strip().upper().replace(" ", "")

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        if not all(payment.info_data.get(key) for key in ("payer", "iban")):
            return False
        try:
            IBANValidator()(self.norm(payment.info_data['iban']))
        except ValidationError:
            return False
        else:
            return True

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return self.payment_refund_supported(payment)

    def payment_presale_render(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        if self.payment_refund_supported(payment):
            try:
                iban = self.norm(pi['iban'])
                return gettext('Bank account {iban}').format(
                    iban=iban[0:2] + '****' + iban[-4:]
                )
            except:
                pass
        return super().payment_presale_render(payment)

    def execute_refund(self, refund: OrderRefund):
        """
        We just keep a created refund object. It will be marked as done using the control view
        for bank transfer refunds.
        """
        if refund.info_data.get('iban'):
            return  # we're already done here

        if refund.payment is None:
            raise ValueError(_("Can only create a bank transfer refund from an existing payment."))

        refund.info_data = {
            'payer': refund.payment.info_data['payer'],
            'iban': self.norm(refund.payment.info_data['iban']),
            'bic': self.norm(refund.payment.info_data['bic']) if refund.payment.info_data.get('bic') else None,
        }
        refund.save(update_fields=["info"])

    def refund_control_render(self, request: HttpRequest, refund: OrderRefund) -> str:
        return self._render_control_info(request, refund.order, refund.info_data)

    class NewRefundForm(forms.Form):
        payer = forms.CharField(
            label=_('Account holder'),
        )
        iban = IBANFormField(
            label=_('IBAN'),
        )
        bic = BICFormField(
            label=_('BIC (optional)'),
            required=False,
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for n, f in self.fields.items():
                f.required = False
                f.widget.is_required = False

        def clean_payer(self):
            val = self.cleaned_data.get('payer')
            if not val:
                raise ValidationError(_("This field is required."))
            return val

        def clean_iban(self):
            val = self.cleaned_data.get('iban')
            if not val:
                raise ValidationError(_("This field is required."))
            return val

    def new_refund_control_form_render(self, request: HttpRequest, order: Order) -> str:
        f = self.NewRefundForm(
            prefix="refund-banktransfer",
            data=request.POST if request.method == "POST" and request.POST.get("refund-banktransfer-iban") else None,
        )
        template = get_template('pretixplugins/banktransfer/new_refund_control_form.html')
        ctx = {
            'form': f,
        }
        return template.render(ctx)

    def new_refund_control_form_process(self, request: HttpRequest, amount: Decimal, order: Order) -> OrderRefund:
        f = self.NewRefundForm(
            prefix="refund-banktransfer",
            data=request.POST
        )
        if not f.is_valid():
            raise ValidationError(_('Your input was invalid, please see below for details.'))
        d = {
            'payer': f.cleaned_data['payer'],
            'iban': self.norm(f.cleaned_data['iban']),
        }
        if f.cleaned_data.get('bic'):
            d['bic'] = f.cleaned_data['bic']
        return OrderRefund(
            order=order,
            payment=None,
            state=OrderRefund.REFUND_STATE_CREATED,
            amount=amount,
            provider=self.identifier,
            info=json.dumps(d)
        )
