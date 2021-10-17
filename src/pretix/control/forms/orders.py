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
# This file contains Apache-licensed contributions copyrighted by: Ayan Ginet, Christopher Dambamuromo, Daniel,
# Jahongir, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from datetime import date, datetime, time
from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.timezone import make_aware, now
from django.utils.translation import (
    gettext_lazy as _, gettext_noop, pgettext_lazy,
)
from django_scopes.forms import SafeModelChoiceField
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_available_placeholders
from pretix.base.forms import I18nModelForm, PlaceholderValidator
from pretix.base.forms.questions import WrappedPhoneNumberPrefixWidget
from pretix.base.forms.widgets import (
    DatePickerWidget, SplitDateTimePickerWidget,
)
from pretix.base.models import (
    Invoice, InvoiceAddress, ItemAddOn, Order, OrderFee, OrderPosition,
    TaxRule,
)
from pretix.base.models.event import SubEvent
from pretix.base.services.pricing import get_price
from pretix.control.forms import SplitDateTimeField
from pretix.control.forms.widgets import Select2
from pretix.helpers.money import change_decimal_field


class ExtendForm(I18nModelForm):
    quota_ignore = forms.BooleanField(
        label=_('Overbook quota'),
        help_text=_('If you check this box, this operation will be performed even if it leads to an overbooked quota '
                    'and you having sold more tickets than you planned!'),
        required=False
    )
    expires = forms.DateField(
        label=_("Expiration date"),
        widget=forms.DateInput(attrs={
            'class': 'datepickerfield',
            'data-is-payment-date': 'true'
        }),
    )

    class Meta:
        model = Order
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.status == Order.STATUS_PENDING or self.instance._is_still_available(now(),
                                                                                             count_waitinglist=False)\
                is True:
            del self.fields['quota_ignore']

    def clean(self):
        data = super().clean()
        if data.get('expires'):
            if isinstance(data['expires'], date):
                data['expires'] = make_aware(datetime.combine(
                    data['expires'],
                    time(hour=23, minute=59, second=59)
                ), self.instance.event.timezone)
            else:
                data['expires'] = data['expires'].replace(hour=23, minute=59, second=59)
            if data['expires'] < now():
                raise ValidationError(_('The new expiry date needs to be in the future.'))
        return data

    def save(self, commit=True):
        self.instance.expires = self.cleaned_data['expires']
        return super().save(commit)


class ForceQuotaConfirmationForm(forms.Form):
    force = forms.BooleanField(
        label=_('Overbook quota and ignore late payment'),
        help_text=_('If you check this box, this operation will be performed even if it leads to an overbooked quota '
                    'and you having sold more tickets than you planned! The operation will also be performed '
                    'regardless of the settings for late payments.'),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop("instance")
        super().__init__(*args, **kwargs)
        quota_success = (
            self.instance.status == Order.STATUS_PENDING or
            self.instance._is_still_available(now(), count_waitinglist=False) is True
        )
        term_last = self.instance.payment_term_last
        term_success = (
            (not term_last or term_last >= now()) and
            (self.instance.status == Order.STATUS_PENDING or self.instance.event.settings.get(
                'payment_term_accept_late'))
        )
        if quota_success and term_success:
            del self.fields['force']


class ConfirmPaymentForm(ForceQuotaConfirmationForm):
    pass


class ReactivateOrderForm(ForceQuotaConfirmationForm):
    pass


class CancelForm(ForceQuotaConfirmationForm):
    send_email = forms.BooleanField(
        required=False,
        label=_('Notify customer by email'),
        initial=True
    )
    cancellation_fee = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        localize=True,
        label=_('Keep a cancellation fee of'),
        help_text=_('If you keep a fee, all positions within this order will be canceled and the order will be reduced '
                    'to a paid cancellation fee. Payment and shipping fees will be canceled as well, so include them '
                    'in your cancellation fee if you want to keep them. Please always enter a gross value, '
                    'tax will be calculated automatically.'),
    )
    cancel_invoice = forms.BooleanField(
        label=_('Generate cancellation for invoice'),
        initial=True,
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        prs = self.instance.payment_refund_sum
        if prs > 0:
            change_decimal_field(self.fields['cancellation_fee'], self.instance.event.currency)
            self.fields['cancellation_fee'].widget.attrs['placeholder'] = floatformat(
                Decimal('0.00'),
                settings.CURRENCY_PLACES.get(self.instance.event.currency, 2)
            )
            self.fields['cancellation_fee'].max_value = prs
        else:
            del self.fields['cancellation_fee']
        if not self.instance.invoices.exists():
            del self.fields['cancel_invoice']

    def clean_cancellation_fee(self):
        val = self.cleaned_data['cancellation_fee'] or Decimal('0.00')
        if val > self.instance.payment_refund_sum:
            raise ValidationError(_('The cancellation fee cannot be higher than the payment credit of this order.'))
        return val


class MarkPaidForm(ConfirmPaymentForm):
    send_email = forms.BooleanField(
        required=False,
        label=_('Notify customer by email'),
        initial=True
    )
    amount = forms.DecimalField(
        required=True,
        max_digits=10, decimal_places=2,
        localize=True,
        label=_('Payment amount'),
    )
    payment_date = forms.DateField(
        required=True,
        label=_('Payment date'),
        widget=DatePickerWidget(),
        initial=now
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        change_decimal_field(self.fields['amount'], self.instance.event.currency)
        self.fields['amount'].initial = max(Decimal('0.00'), self.instance.pending_sum)


class ExporterForm(forms.Form):
    def clean(self):
        data = super().clean()

        for k, v in data.items():
            if isinstance(v, models.Model):
                data[k] = v.pk
            elif isinstance(v, models.QuerySet):
                data[k] = [m.pk for m in v]

        return data


class CommentForm(I18nModelForm):
    class Meta:
        model = Order
        fields = ['comment', 'checkin_attention', 'custom_followup_at']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'class': 'helper-width-100',
            }),
            'custom_followup_at': DatePickerWidget(),
        }


class OtherOperationsForm(forms.Form):
    recalculate_taxes = forms.ChoiceField(
        label=_('Re-calculate taxes'),
        required=False,
        choices=(
            ('', _('Do not re-calculate taxes')),
            ('gross', _('Re-calculate taxes based on address and product settings, keep gross amount the same.')),
            ('net', _('Re-calculate taxes based on address and product settings, keep net amount the same.')),
        ),
        widget=forms.RadioSelect
    )
    reissue_invoice = forms.BooleanField(
        label=_('Issue a new invoice if required'),
        required=False,
        initial=True,
        help_text=_(
            'If an invoice exists for this order and this operation would change its contents, the old invoice will '
            'be canceled and a new invoice will be issued.'
        )
    )
    notify = forms.BooleanField(
        label=_('Notify user'),
        required=False,
        initial=True,
        help_text=_(
            'Send an email to the customer notifying that their order has been changed.'
        )
    )
    ignore_quotas = forms.BooleanField(
        label=_('Allow to overbook quotas when performing this operation'),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('order')
        super().__init__(*args, **kwargs)


class OrderPositionAddForm(forms.Form):
    itemvar = forms.ChoiceField(
        label=_('Product')
    )
    addon_to = forms.ModelChoiceField(
        OrderPosition.all.none(),
        required=False,
        label=_('Add-on to'),
    )
    seat = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': _('General admission'), 'data-seat-guid-field': 'true'}),
        label=_('Seat')
    )
    used_membership = forms.ChoiceField(
        label=_('Membership'),
        required=False,
    )
    price = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        localize=True,
        label=_('Gross price'),
        help_text=_("Including taxes, if any. Keep empty for the product's default price")
    )
    subevent = forms.ModelChoiceField(
        SubEvent.objects.none(),
        label=pgettext_lazy('subevent', 'Date'),
        required=True,
        empty_label=None
    )

    def __init__(self, *args, **kwargs):
        self.items = kwargs.pop('items')
        order = kwargs.pop('order')
        super().__init__(*args, **kwargs)

        try:
            ia = order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None

        choices = []
        for i in self.items:
            pname = str(i)
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())
            if i.tax_rule:  # performance optimization
                i.tax_rule.event = order.event
            if variations:
                for v in variations:
                    p = get_price(i, v, invoice_address=ia)
                    choices.append(('%d-%d' % (i.pk, v.pk),
                                    '%s – %s (%s)' % (pname, v.value, p.print(order.event.currency))))
            else:
                p = get_price(i, invoice_address=ia)
                choices.append((str(i.pk), '%s (%s)' % (pname, p.print(order.event.currency))))
        self.fields['itemvar'].choices = choices
        if order.event.cache.get_or_set(
                'has_addon_products',
                default=lambda: ItemAddOn.objects.filter(base_item__event=order.event).exists(),
                timeout=300
        ):
            self.fields['addon_to'].queryset = order.positions.filter(addon_to__isnull=True).select_related(
                'item', 'variation'
            )
        else:
            del self.fields['addon_to']

        if order.event.has_subevents:
            self.fields['subevent'].queryset = order.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': order.event.slug,
                        'organizer': order.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'Date')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
            self.fields['subevent'].required = True
        else:
            del self.fields['subevent']
        change_decimal_field(self.fields['price'], order.event.currency)

        choices = [
            ('', ''),
        ]
        if order.customer:
            self.memberships = list(order.customer.memberships.all())
            for m in self.memberships:
                choices.append((str(m.pk), str(m)))
        self.fields['used_membership'].choices = choices

    def clean(self):
        d = super().clean()
        if d['used_membership']:
            d['used_membership'] = [m for m in self.memberships if str(m.pk) == d['used_membership']][0]
        else:
            d['used_membership'] = None
        return d


class OrderPositionAddFormset(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.order = kwargs.pop('order', None)
        self.items = kwargs.pop('items')
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['order'] = self.order
        kwargs['items'] = self.items
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            order=self.order,
            items=self.items,
        )
        self.add_fields(form, None)
        return form


class OrderPositionChangeForm(forms.Form):
    itemvar = forms.ChoiceField(
        required=False,
    )
    subevent = forms.ModelChoiceField(
        SubEvent.objects.none(),
        required=False,
        empty_label=_('(Unchanged)')
    )
    seat = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': _('(Unchanged)'), 'data-seat-guid-field': 'true'})
    )
    price = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        localize=True,
        label=_('New price (gross)')
    )
    used_membership = forms.ChoiceField(
        required=False,
    )
    tax_rule = forms.ModelChoiceField(
        TaxRule.objects.none(),
        required=False,
        empty_label=_('(Unchanged)')
    )
    operation_secret = forms.BooleanField(
        required=False,
        label=_('Generate a new secret')
    )
    operation_cancel = forms.BooleanField(
        required=False,
        label=_('Cancel this position')
    )
    operation_split = forms.BooleanField(
        required=False,
        label=_('Split into new order')
    )

    @staticmethod
    def taxrule_label_from_instance(obj):
        return f"{obj.name} ({obj.rate} %)"

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance')
        items = kwargs.pop('items')
        initial = kwargs.get('initial', {})

        initial['price'] = instance.price

        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        if instance.order.event.has_subevents:
            self.fields['subevent'].queryset = instance.order.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': instance.order.event.slug,
                        'organizer': instance.order.event.organizer.slug,
                    }),
                    'data-placeholder': _('(Unchanged)')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        else:
            del self.fields['subevent']

        self.fields['tax_rule'].queryset = instance.event.tax_rules.all()
        self.fields['tax_rule'].label_from_instance = self.taxrule_label_from_instance

        if not instance.seat and not (
                instance.item.seat_category_mappings.filter(subevent=instance.subevent).exists()
        ):
            del self.fields['seat']

        choices = [
            ('', _('(Unchanged)'))
        ]
        for i in items:
            pname = str(i)
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())

            if variations:
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk),
                                    '%s – %s' % (pname, v.value)))
            else:
                choices.append((str(i.pk), pname))
        self.fields['itemvar'].choices = choices
        change_decimal_field(self.fields['price'], instance.order.event.currency)

        choices = [
            ('', _('(Unchanged)')),
            ('CLEAR', _('(No membership)')),
        ]
        if instance.order.customer:
            self.memberships = list(instance.order.customer.memberships.all())
            for m in self.memberships:
                choices.append((str(m.pk), str(m)))
        self.fields['used_membership'].choices = choices

    def clean(self):
        d = super().clean()
        if d['used_membership'] and d['used_membership'] != 'CLEAR':
            d['used_membership'] = [m for m in self.memberships if str(m.pk) == d['used_membership']][0]
        elif not d['used_membership']:
            d['used_membership'] = None
        return d


class OrderFeeChangeForm(forms.Form):
    value = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        localize=True,
        label=_('New price (gross)')
    )
    tax_rule = forms.ModelChoiceField(
        TaxRule.objects.none(),
        required=False,
        empty_label=_('(Unchanged)')
    )
    operation_cancel = forms.BooleanField(
        required=False,
        label=_('Remove this fee')
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance')
        initial = kwargs.get('initial', {})

        initial['value'] = instance.value
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        self.fields['tax_rule'].queryset = instance.order.event.tax_rules.all()
        change_decimal_field(self.fields['value'], instance.order.event.currency)


class OrderContactForm(forms.ModelForm):
    regenerate_secrets = forms.BooleanField(required=False, label=_('Invalidate secrets'),
                                            help_text=_('Regenerates the order and ticket secrets. You will '
                                                        'need to re-send the link to the order page to the user and '
                                                        'the user will need to download his tickets again. The old '
                                                        'versions will be invalid.'))

    class Meta:
        model = Order
        fields = ['customer', 'email', 'email_known_to_work', 'phone']
        widgets = {
            'phone': WrappedPhoneNumberPrefixWidget(),
        }
        field_classes = {
            'customer': SafeModelChoiceField,
        }

    def __init__(self, *args, **kwargs):
        customers = kwargs.pop('customers')
        super().__init__(*args, **kwargs)
        if not self.instance.event.settings.order_phone_asked and not self.instance.phone:
            del self.fields['phone']

        if customers:
            self.fields['customer'].queryset = self.instance.event.organizer.customers.all()
            self.fields['customer'].widget = Select2(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:organizer.customers.select2', kwargs={
                        'organizer': self.instance.event.organizer.slug,
                    }),
                    'data-placeholder': _('Customer')
                }
            )
            self.fields['customer'].widget.choices = self.fields['customer'].choices
            self.fields['customer'].required = False
        else:
            del self.fields['customer']


class OrderLocaleForm(forms.ModelForm):
    locale = forms.ChoiceField()

    class Meta:
        model = Order
        fields = ['locale']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        locale_names = dict(settings.LANGUAGES)
        self.fields['locale'].choices = [(a, locale_names[a]) for a in self.instance.event.settings.locales]


class OrderMailForm(forms.Form):
    subject = forms.CharField(
        label=_("Subject"),
        required=True
    )
    attach_tickets = forms.BooleanField(
        label=_("Attach tickets"),
        help_text=_("Will be ignored if all tickets in this order exceed a given size limit to ensure email deliverability."),
        required=False
    )
    attach_invoices = forms.ModelMultipleChoiceField(
        label=_("Attach invoices"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        queryset=Invoice.objects.none()
    )

    def _set_field_placeholders(self, fn, base_parameters):
        phs = [
            '{%s}' % p
            for p in sorted(get_available_placeholders(self.order.event, base_parameters).keys())
        ]
        ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(phs)
        )

    def __init__(self, *args, **kwargs):
        order = self.order = kwargs.pop('order')
        super().__init__(*args, **kwargs)
        self.fields['sendto'] = forms.EmailField(
            label=_("Recipient"),
            required=True,
            initial=order.email
        )
        self.fields['sendto'].widget.attrs['readonly'] = 'readonly'
        self.fields['message'] = forms.CharField(
            label=_("Message"),
            required=True,
            widget=forms.Textarea,
            initial=order.event.settings.mail_text_order_custom_mail.localize(order.locale),
        )
        self.fields['attach_invoices'].queryset = order.invoices.all()
        self._set_field_placeholders('message', ['event', 'order'])


class OrderPositionMailForm(OrderMailForm):
    def __init__(self, *args, **kwargs):
        position = self.position = kwargs.pop('position')
        super().__init__(*args, **kwargs)
        del self.fields['attach_invoices']
        self.fields['sendto'].initial = position.attendee_email
        self.fields['message'] = forms.CharField(
            label=_("Message"),
            required=True,
            widget=forms.Textarea,
            initial=self.order.event.settings.mail_text_order_custom_mail.localize(self.order.locale),
        )
        self._set_field_placeholders('message', ['event', 'order', 'position'])


class OrderRefundForm(forms.Form):
    action = forms.ChoiceField(
        required=False,
        widget=forms.RadioSelect,
        choices=(
            ('mark_refunded', _('Cancel the order. All tickets will no longer work. This can not be reverted.')),
            ('mark_pending', _('Mark the order as pending and allow the user to pay the open amount with another '
                               'payment method.')),
            ('do_nothing', _('Do nothing and keep the order as it is.')),
        )
    )
    mode = forms.ChoiceField(
        required=False,
        widget=forms.RadioSelect,
        choices=(
            ('full', 'Full refund'),
            ('partial', 'Partial refund'),
        )
    )
    partial_amount = forms.DecimalField(
        required=False, max_digits=10, decimal_places=2,
        localize=True
    )

    def __init__(self, *args, **kwargs):
        self.order = kwargs.pop('order')
        super().__init__(*args, **kwargs)
        change_decimal_field(self.fields['partial_amount'], self.order.event.currency)
        if self.order.status == Order.STATUS_CANCELED:
            del self.fields['action']

    def clean_partial_amount(self):
        max_amount = self.order.payment_refund_sum
        val = self.cleaned_data.get('partial_amount')
        if val is not None and (val > max_amount or val <= 0):
            raise ValidationError(_('The refund amount needs to be positive and less than {}.').format(max_amount))
        return val

    def clean(self):
        data = self.cleaned_data
        if data.get('mode') == 'partial' and not data.get('partial_amount'):
            raise ValidationError(_('You need to specify an amount for a partial refund.'))
        return data


class EventCancelForm(forms.Form):
    subevent = forms.ModelChoiceField(
        SubEvent.objects.none(),
        label=pgettext_lazy('subevent', 'Date'),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )
    all_subevents = forms.BooleanField(
        label=_('Cancel all dates'),
        initial=False,
        required=False,
    )
    subevents_from = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
            'data-inverse-dependency': '#id_all_subevents',
        }),
        label=pgettext_lazy('subevent', 'All dates starting at or after'),
        required=False,
    )
    subevents_to = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
            'data-inverse-dependency': '#id_all_subevents',
        }),
        label=pgettext_lazy('subevent', 'All dates starting before'),
        required=False,
    )
    auto_refund = forms.BooleanField(
        label=_('Automatically refund money if possible'),
        initial=True,
        required=False
    )
    manual_refund = forms.BooleanField(
        label=_('Create manual refund if the payment method does not support automatic refunds'),
        widget=forms.CheckboxInput(attrs={'data-display-dependency': '#id_auto_refund'}),
        initial=True,
        required=False,
        help_text=_('If checked, all payments with a payment method not supporting automatic refunds will be on your '
                    'manual refund to-do list. Do not check if you want to refund some of the orders by offsetting '
                    'with different orders or issuing gift cards.')
    )
    refund_as_giftcard = forms.BooleanField(
        label=_('Refund order value to a gift card instead instead of the original payment method'),
        widget=forms.CheckboxInput(attrs={'data-display-dependency': '#id_auto_refund'}),
        initial=False,
        required=False,
    )
    gift_card_expires = SplitDateTimeField(
        label=_('Gift card validity'),
        required=False,
        widget=SplitDateTimePickerWidget(
            attrs={'data-display-dependency': '#id_refund_as_giftcard'},
        )
    )
    gift_card_conditions = forms.CharField(
        label=_('Special terms and conditions'),
        required=False,
        widget=forms.Textarea(
            attrs={'rows': 2, 'data-display-dependency': '#id_refund_as_giftcard'},
        )
    )
    keep_fee_fixed = forms.DecimalField(
        label=_("Keep a fixed cancellation fee"),
        max_digits=10, decimal_places=2,
        required=False
    )
    keep_fee_per_ticket = forms.DecimalField(
        label=_("Keep a fixed cancellation fee per ticket"),
        help_text=_("Free tickets and add-on products are not counted"),
        max_digits=10, decimal_places=2,
        required=False
    )
    keep_fee_percentage = forms.DecimalField(
        label=_("Keep a percentual cancellation fee"),
        max_digits=10, decimal_places=2,
        required=False
    )
    keep_fees = forms.MultipleChoiceField(
        label=_("Keep fees"),
        widget=forms.CheckboxSelectMultiple,
        choices=[(k, v) for k, v in OrderFee.FEE_TYPES if k != OrderFee.FEE_TYPE_GIFTCARD],
        help_text=_('The selected types of fees will not be refunded but instead added to the cancellation fee. Fees '
                    'are never refunded in when an order in an event series is only partially canceled since it '
                    'consists of tickets for multiple dates.'),
        required=False,
    )
    send = forms.BooleanField(
        label=_("Send information via email"),
        required=False
    )
    send_subject = forms.CharField()
    send_message = forms.CharField()
    send_waitinglist = forms.BooleanField(
        label=_("Send information to waiting list"),
        required=False
    )
    send_waitinglist_subject = forms.CharField()
    send_waitinglist_message = forms.CharField()

    def _set_field_placeholders(self, fn, base_parameters):
        phs = [
            '{%s}' % p
            for p in sorted(get_available_placeholders(self.event, base_parameters).keys())
        ]
        ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(phs)
        )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        kwargs.setdefault('initial', {})
        kwargs['initial']['gift_card_expires'] = self.event.organizer.default_gift_card_expiry
        super().__init__(*args, **kwargs)
        self.fields['send_subject'] = I18nFormField(
            label=_("Subject"),
            required=True,
            widget_kwargs={'attrs': {'data-display-dependency': '#id_send'}},
            initial=_('Canceled: {event}'),
            widget=I18nTextInput,
            locales=self.event.settings.get('locales'),
        )
        self.fields['send_message'] = I18nFormField(
            label=_('Message'),
            widget=I18nTextarea,
            required=True,
            widget_kwargs={'attrs': {'data-display-dependency': '#id_send'}},
            locales=self.event.settings.get('locales'),
            initial=LazyI18nString.from_gettext(gettext_noop(
                'Hello,\n\n'
                'with this email, we regret to inform you that {event} has been canceled.\n\n'
                'We will refund you {refund_amount} to your original payment method.\n\n'
                'You can view the current state of your order here:\n\n{url}\n\nBest regards,\n\n'
                'Your {event} team'
            ))
        )

        self._set_field_placeholders('send_subject', ['event_or_subevent', 'refund_amount', 'position_or_address',
                                                      'order', 'event'])
        self._set_field_placeholders('send_message', ['event_or_subevent', 'refund_amount', 'position_or_address',
                                                      'order', 'event'])
        self.fields['send_waitinglist_subject'] = I18nFormField(
            label=_("Subject"),
            required=True,
            initial=_('Canceled: {event}'),
            widget=I18nTextInput,
            widget_kwargs={'attrs': {'data-display-dependency': '#id_send_waitinglist'}},
            locales=self.event.settings.get('locales'),
        )
        self.fields['send_waitinglist_message'] = I18nFormField(
            label=_('Message'),
            widget=I18nTextarea,
            required=True,
            locales=self.event.settings.get('locales'),
            widget_kwargs={'attrs': {'data-display-dependency': '#id_send_waitinglist'}},
            initial=LazyI18nString.from_gettext(gettext_noop(
                'Hello,\n\n'
                'with this email, we regret to inform you that {event} has been canceled.\n\n'
                'You will therefore not receive a ticket from the waiting list.\n\n'
                'Best regards,\n\n'
                'Your {event} team'
            ))
        )
        self._set_field_placeholders('send_waitinglist_subject', ['event_or_subevent', 'event'])
        self._set_field_placeholders('send_waitinglist_message', ['event_or_subevent', 'event'])

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-inverse-dependency': '#id_all_subevents',
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        else:
            del self.fields['subevent']
            del self.fields['all_subevents']
        change_decimal_field(self.fields['keep_fee_fixed'], self.event.currency)

    def clean(self):
        d = super().clean()
        if d.get('subevent') and d.get('subevents_from'):
            raise ValidationError(pgettext_lazy('subevent', 'Please either select a specific date or a date range, not both.'))
        if d.get('all_subevents') and d.get('subevent_from'):
            raise ValidationError(pgettext_lazy('subevent', 'Please either select all dates or a date range, not both.'))
        if bool(d.get('subevents_from')) != bool(d.get('subevents_to')):
            raise ValidationError(pgettext_lazy('subevent', 'If you set a date range, please set both a start and an end.'))
        if self.event.has_subevents and not d['subevent'] and not d['all_subevents'] and not d.get('subevents_from'):
            raise ValidationError(_('Please confirm that you want to cancel ALL dates in this event series.'))
        return d
