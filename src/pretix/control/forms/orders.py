from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _

from pretix.base.email import get_available_placeholders
from pretix.base.forms import I18nModelForm, PlaceholderValidator
from pretix.base.forms.widgets import DatePickerWidget
from pretix.base.models import (
    InvoiceAddress, ItemAddOn, Order, OrderPosition, Seat,
)
from pretix.base.models.event import SubEvent
from pretix.base.services.pricing import get_price
from pretix.control.forms.widgets import Select2
from pretix.helpers.money import change_decimal_field


class ExtendForm(I18nModelForm):
    quota_ignore = forms.BooleanField(
        label=_('Overbook quota'),
        help_text=_('If you check this box, this operation will be performed even if it leads to an overbooked quota '
                    'and you having sold more tickets than you planned!'),
        required=False
    )

    class Meta:
        model = Order
        fields = ['expires']
        widgets = {
            'expires': forms.DateInput(attrs={
                'class': 'datepickerfield',
                'data-is-payment-date': 'true'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.status == Order.STATUS_PENDING or self.instance._is_still_available(now(),
                                                                                             count_waitinglist=False)\
                is True:
            del self.fields['quota_ignore']

    def clean(self):
        data = super().clean()
        data['expires'] = data['expires'].replace(hour=23, minute=59, second=59)
        if data['expires'] < now():
            raise ValidationError(_('The new expiry date needs to be in the future.'))
        return data


class ConfirmPaymentForm(forms.Form):
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


class CancelForm(ConfirmPaymentForm):
    send_email = forms.BooleanField(
        required=False,
        label=_('Notify user by e-mail'),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        prs = self.instance.payment_refund_sum
        if prs > 0:
            change_decimal_field(self.fields['cancellation_fee'], self.instance.event.currency)
            self.fields['cancellation_fee'].initial = Decimal('0.00')
            self.fields['cancellation_fee'].max_value = prs
        else:
            del self.fields['cancellation_fee']

    def clean_cancellation_fee(self):
        val = self.cleaned_data['cancellation_fee']
        if val > self.instance.payment_refund_sum:
            raise ValidationError(_('The cancellation fee cannot be higher than the payment credit of this order.'))
        return val


class MarkPaidForm(ConfirmPaymentForm):
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
        fields = ['comment', 'checkin_attention']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'class': 'helper-width-100',
            }),
        }


class OtherOperationsForm(forms.Form):
    recalculate_taxes = forms.BooleanField(
        label=_('Re-calculate taxes'),
        required=False,
        help_text=_(
            'This operation re-checks if taxes should be paid to the items due to e.g. configured reverse charge rules '
            'and changes the prices and tax values accordingly. This is useful e.g. after an invoice address change. '
            'Use with care and only if you need to. Note that rounding differences might occur in this procedure.'
        )
    )
    reissue_invoice = forms.BooleanField(
        label=_('Issue a new invoice if required'),
        required=False,
        initial=True,
        help_text=_(
            'If an invoice exists for this order and this operation would change its contents, the old invoice will '
            'be cancelled and a new invoice will be issued.'
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
    seat = forms.ModelChoiceField(
        Seat.objects.none(),
        required=False,
        label=_('Seat'),
        empty_label=_('General admission')
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
        order = kwargs.pop('order')
        super().__init__(*args, **kwargs)

        try:
            ia = order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None

        choices = []
        for i in order.event.items.prefetch_related('variations').all():
            pname = str(i)
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())
            if variations:
                for v in variations:
                    p = get_price(i, v, invoice_address=ia)
                    choices.append(('%d-%d' % (i.pk, v.pk),
                                    '%s – %s (%s)' % (pname, v.value, p.print(order.event.currency))))
            else:
                p = get_price(i, invoice_address=ia)
                choices.append((str(i.pk), '%s (%s)' % (pname, p.print(order.event.currency))))
        self.fields['itemvar'].choices = choices
        if ItemAddOn.objects.filter(base_item__event=order.event).exists():
            self.fields['addon_to'].queryset = order.positions.filter(addon_to__isnull=True).select_related(
                'item', 'variation'
            )
        else:
            del self.fields['addon_to']

        self.fields['seat'].queryset = order.event.seats.all()
        self.fields['seat'].widget = Select2(
            attrs={
                'data-model-select2': 'seat',
                'data-select2-url': reverse('control:event.seats.select2', kwargs={
                    'event': order.event.slug,
                    'organizer': order.event.organizer.slug,
                }),
                'data-placeholder': _('General admission')
            }
        )
        self.fields['seat'].widget.choices = self.fields['seat'].choices

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


class OrderPositionAddFormset(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['order'] = self.order
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
            order=self.order,
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
    seat = forms.ModelChoiceField(
        Seat.objects.none(),
        required=False,
        empty_label=_('(Unchanged)')
    )
    price = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        localize=True,
        label=_('New price (gross)')
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

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance')
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

        if instance.seat:
            self.fields['seat'].queryset = instance.order.event.seats.all()
            self.fields['seat'].widget = Select2(
                attrs={
                    'data-model-select2': 'seat',
                    'data-select2-url': reverse('control:event.seats.select2', kwargs={
                        'event': instance.order.event.slug,
                        'organizer': instance.order.event.organizer.slug,
                    }),
                    'data-placeholder': _('(Unchanged)')
                }
            )
            self.fields['seat'].widget.choices = self.fields['seat'].choices
        else:
            del self.fields['seat']

        choices = [
            ('', _('(Unchanged)'))
        ]
        for i in instance.order.event.items.prefetch_related('variations').all():
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

    def clean(self):
        if self.cleaned_data.get('operation') == 'price' and not self.cleaned_data.get('price', '') != '':
            raise ValidationError(_('You need to enter a price if you want to change the product price.'))


class OrderContactForm(forms.ModelForm):
    regenerate_secrets = forms.BooleanField(required=False, label=_('Invalidate secrets'),
                                            help_text=_('Regenerates the order and ticket secrets. You will '
                                                        'need to re-send the link to the order page to the user and '
                                                        'the user will need to download his tickets again. The old '
                                                        'versions will be invalid.'))

    class Meta:
        model = Order
        fields = ['email', 'email_known_to_work']


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
        self._set_field_placeholders('message', ['event', 'order'])


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
