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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy as _
from i18nfield.fields import I18nFormField, I18nTextarea
from i18nfield.forms import I18nTextInput
from i18nfield.strings import LazyI18nString
from localflavor.generic.forms import BICFormField, IBANFormField
from localflavor.generic.validators import IBANValidator
from text_unidecode import unidecode

from pretix.base.email import get_available_placeholders, get_email_context
from pretix.base.forms import PlaceholderValidator
from pretix.base.i18n import language
from pretix.base.models import InvoiceAddress, Order, OrderPayment, OrderRefund
from pretix.base.payment import BasePaymentProvider
from pretix.base.services.mail import SendMailException, mail, render_mail
from pretix.base.templatetags.money import money_filter
from pretix.helpers.format import format_map
from pretix.plugins.banktransfer.templatetags.ibanformat import ibanformat
from pretix.presale.views.cart import cart_session


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
                help_text=_(
                    'Please note: special characters other than letters, numbers, and some punctuation can cause problems with some banks.'),
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
                widget_kwargs={'attrs': {
                    'rows': '2',
                }},
                required=False,
            )),
            ('refund_iban_blocklist', forms.CharField(
                label=_('IBAN blocklist for refunds'),
                required=False,
                widget=forms.Textarea(attrs={'rows': 4}),
                help_text=_('Put one IBAN or IBAN prefix per line. The system will not attempt to send refunds to any '
                            'of these IBANs. Useful e.g. if you receive a lot of "forwarded payments" by a third-party payment '
                            'provider. You can also list country codes such as "GB" if you never want to send refunds to '
                            'IBANs from a specific country.')
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
        phs = [
            '{%s}' % p
            for p in sorted(get_available_placeholders(self.event, ['event', 'order', 'invoice']).keys())
        ]
        phs_ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        more_fields = OrderedDict([
            ('invoice_email',
             forms.BooleanField(
                 label=_('Allow users to enter an additional email address that the invoice will be sent to.'),
                 help_text=_(
                     'This requires that the invoice creation settings allow the invoice to be created right after '
                     'the payment method was chosen. Only the invoice will be sent to this email address, subsequent '
                     'invoice corrections will not be sent automatically. Only the invoice will be sent, no additional '
                     'information.'
                 ),
                 required=False,
             )),
            ('invoice_email_subject',
             I18nFormField(
                 label=_('Invoice email subject'),
                 widget=I18nTextInput,
                 widget_kwargs={'attrs': {
                     'data-display-dependency': '#id_payment_banktransfer_invoice_email',
                     'data-required-if': '#id_payment_banktransfer_invoice_email',
                 }},
                 validators=[PlaceholderValidator(phs)],
                 help_text=phs_ht,
                 required=False
             )),
            ('invoice_email_text',
             I18nFormField(
                 label=_('Invoice email text'),
                 widget=I18nTextarea,
                 widget_kwargs={'attrs': {
                     'rows': '8',
                     'data-display-dependency': '#id_payment_banktransfer_invoice_email',
                     'data-required-if': '#id_payment_banktransfer_invoice_email',
                 }},
                 validators=[PlaceholderValidator(phs)],
                 help_text=phs_ht,
                 required=False
             )),
        ])
        more_fields_first = OrderedDict([
            ('_restricted_business',
             forms.BooleanField(
                 label=_('Restrict to business customers'),
                 help_text=_('Only allow choosing this payment provider for customers who enter an invoice address '
                             'and select "Business or institutional customer".'),
                 required=False,
             )),
        ])

        d = OrderedDict(
            list(super().settings_form_fields.items()) +
            list(more_fields_first.items()) +
            list(BankTransfer.form_fields().items()) +
            list(more_fields.items())
        )
        d.move_to_end('invoice_immediately', last=False)
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
            for f in (
                'bank_details_sepa_name', 'bank_details_sepa_bank', 'bank_details_sepa_bic',
                'bank_details_sepa_iban'
            ):
                if not cleaned_data.get('payment_banktransfer_%s' % f):
                    raise ValidationError(
                        {'payment_banktransfer_%s' % f: _('Please fill out your bank account details.')})
        else:
            if not cleaned_data.get('payment_banktransfer_bank_details'):
                raise ValidationError(
                    {'payment_banktransfer_bank_details': _('Please enter your bank account details.')})
        return cleaned_data

    @cached_property
    def _invoice_email_asked(self):
        return (
            self.settings.get('invoice_email', as_type=bool) and
            (self.event.settings.invoice_generate == 'True' or (
                self.event.settings.invoice_generate == 'paid' and
                self.settings.get('invoice_immediately', as_type=bool)
            ))
        )

    def is_allowed(self, request: HttpRequest, total: Decimal=None) -> bool:
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

        restricted_business = self.settings.get('_restricted_business', as_type=bool)
        if restricted_business:
            ia = get_invoice_address()
            if not ia.is_business:
                return False

        return super().is_allowed(request, total)

    @property
    def payment_form_fields(self) -> dict:
        if self._invoice_email_asked:
            return {
                'send_invoice': forms.BooleanField(
                    label=_('Please additionally send my invoice directly to our accounting department'),
                    required=False,
                ),
                'send_invoice_to': forms.EmailField(
                    label=_('Invoice recipient e-mail'),
                    required=False,
                    help_text=_('The invoice recipient will receive an email which includes the invoice and your email '
                                'address so they know who placed this order.'),
                    widget=forms.EmailInput(
                        attrs={
                            'data-display-dependency': '#id_payment_banktransfer-send_invoice',
                        }
                    )
                ),
            }
        else:
            return {}

    def payment_form_render(self, request, total=None, order=None) -> str:
        template = get_template('pretixplugins/banktransfer/checkout_payment_form.html')
        form = self.payment_form(request)
        ctx = {
            'request': request,
            'form': form,
            'event': self.event,
            'settings': self.settings,
            'code': self._code(order) if order else None,
            'details': self.settings.get('bank_details', as_type=LazyI18nString),
        }
        return template.render(ctx)

    def checkout_prepare(self, request, total):
        form = self.payment_form(request)
        if form.is_valid():
            for k, v in form.cleaned_data.items():
                request.session['payment_%s_%s' % (self.identifier, k)] = v
            return True
        else:
            return False

    def send_invoice_to_alternate_email(self, order, invoice, email):
        """
        Sends an email to the alternate invoice address.
        """
        with language(order.locale, self.event.settings.region):
            context = get_email_context(event=self.event,
                                        order=order,
                                        invoice=invoice,
                                        event_or_subevent=self.event,
                                        invoice_address=order.invoice_address)
            template = self.settings.get('invoice_email_text', as_type=LazyI18nString)
            subject = self.settings.get('invoice_email_subject', as_type=LazyI18nString)

            try:
                email_content = render_mail(template, context)
                subject = format_map(subject, context)
                mail(
                    email,
                    subject,
                    template,
                    context=context,
                    event=self.event,
                    locale=order.locale,
                    order=order,
                    invoices=[invoice],
                    attach_tickets=False,
                    auto_email=True,
                    attach_ical=False,
                    plain_text_only=True,
                    no_order_links=True,
                )
            except SendMailException:
                raise
            else:
                order.log_action(
                    'pretix.plugins.banktransfer.order.email.invoice',
                    data={
                        'subject': subject,
                        'message': email_content,
                        'position': None,
                        'recipient': email,
                        'invoices': invoice.pk,
                        'attach_tickets': False,
                        'attach_ical': False,
                    }
                )

    def execute_payment(self, request: HttpRequest, payment: OrderPayment) -> str:
        send_invoice = (
            self._invoice_email_asked and
            request and
            request.session.get('payment_%s_%s' % (self.identifier, 'send_invoice')) and
            request.session.get('payment_%s_%s' % (self.identifier, 'send_invoice_to'))
        )
        if send_invoice:
            recipient = request.session.get('payment_%s_%s' % (self.identifier, 'send_invoice_to'))
            payment.info_data = {
                'send_invoice_to': recipient,
            }
            payment.save(update_fields=['info'])
            i = payment.order.invoices.filter(is_cancellation=False).last()
            if i:
                self.send_invoice_to_alternate_email(payment.order, i, recipient)
        if request:
            request.session.pop('payment_%s_%s' % (self.identifier, 'send_invoice'), None)
            request.session.pop('payment_%s_%s' % (self.identifier, 'send_invoice_to'), None)

    def payment_prepare(self, request: HttpRequest, payment: OrderPayment):
        return self.checkout_prepare(request, payment.amount)

    def payment_is_valid_session(self, request):
        return True

    def checkout_confirm_render(self, request, order=None):
        template = get_template('pretixplugins/banktransfer/checkout_confirm.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'code': self._code(order) if order else None,
            'details': self.settings.get('bank_details', as_type=LazyI18nString),
        }
        return template.render(ctx)

    def order_pending_mail_render(self, order, payment) -> str:
        t = gettext("Please transfer the full amount to the following bank account:")
        t += "\n\n"

        md_nl2br = "  \n"
        if self.settings.get('bank_details_type') == 'sepa':
            bankdetails = (
                (_("Reference"), self._code(order)),
                (_("Amount"), money_filter(payment.amount, self.event.currency)),
                (_("Account holder"), self.settings.get('bank_details_sepa_name')),
                (_("IBAN"), ibanformat(self.settings.get('bank_details_sepa_iban'))),
                (_("BIC"), self.settings.get('bank_details_sepa_bic')),
                (_("Bank"), self.settings.get('bank_details_sepa_bank')),
            )
        else:
            bankdetails = (
                (_("Reference"), self._code(order)),
                (_("Amount"), money_filter(payment.amount, self.event.currency)),
            )
        t += md_nl2br.join([f"**{k}:** {v}" for k, v in bankdetails])
        if self.settings.get('bank_details', as_type=LazyI18nString):
            t += md_nl2br
        t += str(self.settings.get('bank_details', as_type=LazyI18nString))
        return t

    def swiss_qrbill(self, payment):
        if not self.settings.get('bank_details_sepa_iban') or not self.settings.get('bank_details_sepa_iban')[:2] in ('CH', 'LI'):
            return
        if self.event.currency not in ('EUR', 'CHF'):
            return
        if not self.event.settings.invoice_address_from or not self.event.settings.invoice_address_from_country:
            return

        data_fields = [
            'SPC',
            '0200',
            '1',
            self.settings.get('bank_details_sepa_iban'),
            'K',
            self.settings.get('bank_details_sepa_name')[:70],
            self.event.settings.invoice_address_from.replace('\n', ', ')[:70],
            (self.event.settings.invoice_address_from_zipcode + ' ' + self.event.settings.invoice_address_from_city)[:70],
            '',
            '',
            str(self.event.settings.invoice_address_from_country),
            '',  # rfu
            '',  # rfu
            '',  # rfu
            '',  # rfu
            '',  # rfu
            '',  # rfu
            '',  # rfu
            str(payment.amount),
            self.event.currency,
            '',  # debtor address
            '',  # debtor address
            '',  # debtor address
            '',  # debtor address
            '',  # debtor address
            '',  # debtor address
            '',  # debtor address
            'NON',
            '',  # structured reference
            self._code(payment.order),
            'EPD',
        ]

        data_fields = [unidecode(d or '') for d in data_fields]
        return '\r\n'.join(data_fields)

    def payment_pending_render(self, request: HttpRequest, payment: OrderPayment):
        template = get_template('pretixplugins/banktransfer/pending.html')
        ctx = {
            'event': self.event,
            'code': self._code(payment.order),
            'order': payment.order,
            'amount': payment.amount,
            'settings': self.settings,
            'swiss_qrbill': self.swiss_qrbill(payment),
            'eu_barcodes': self.event.currency == 'EUR',
            'pending_description': self.settings.get('pending_description', as_type=LazyI18nString),
            'details': self.settings.get('bank_details', as_type=LazyI18nString),
        }
        ctx['any_barcodes'] = ctx['swiss_qrbill'] or ctx['eu_barcodes']
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
        if 'send_invoice_to' in d:
            d['send_invoice_to'] = '█'
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
            iban = self.norm(payment.info_data['iban'])
            IBANValidator()(iban)
        except ValidationError:
            return False
        else:
            return not any(iban.startswith(b) for b in (self.settings.refund_iban_blocklist or '').splitlines() if b)

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return self.payment_refund_supported(payment)

    def payment_control_render_short(self, payment: OrderPayment) -> str:
        pi = payment.info_data or {}
        r = pi.get('payer', '')
        if pi.get('iban'):
            if r:
                r += ' / '
            r += pi.get('iban')
        if pi.get('bic'):
            if r:
                r += ' / '
            r += pi.get('bic')
        return r

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
