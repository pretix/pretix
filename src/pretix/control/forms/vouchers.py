from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, Voucher
from pretix.control.forms import SplitDateTimeField, SplitDateTimePickerWidget
from pretix.control.forms.widgets import Select2, Select2ItemVarQuota
from pretix.control.signals import voucher_form_validation
from pretix.helpers.models import modelcopy


class FakeChoiceField(forms.ChoiceField):
    def valid_value(self, value):
        return True


class VoucherForm(I18nModelForm):
    itemvar = FakeChoiceField(
        label=_("Product"),
        help_text=_(
            "This product is added to the user's cart if the voucher is redeemed."
        ),
        required=True
    )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'code', 'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag',
            'comment', 'max_usages', 'price_mode', 'subevent', 'show_hidden_items'
        ]
        field_classes = {
            'valid_until': SplitDateTimeField,
            'subevent': SafeModelChoiceField,
        }
        widgets = {
            'valid_until': SplitDateTimePickerWidget(),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        initial = kwargs.get('initial')
        if instance:
            self.initial_instance_data = modelcopy(instance)
            try:
                if instance.variation:
                    initial['itemvar'] = '%d-%d' % (instance.item.pk, instance.variation.pk)
                elif instance.item:
                    initial['itemvar'] = str(instance.item.pk)
                elif instance.quota:
                    initial['itemvar'] = 'q-%d' % instance.quota.pk
            except Item.DoesNotExist:
                pass
        else:
            self.initial_instance_data = None
        super().__init__(*args, **kwargs)

        if instance.event.has_subevents:
            self.fields['subevent'].queryset = instance.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': instance.event.slug,
                        'organizer': instance.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'Date')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
            self.fields['subevent'].required = False
        elif 'subevent':
            del self.fields['subevent']

        choices = []
        if 'itemvar' in initial or (self.data and 'itemvar' in self.data):
            iv = self.data.get('itemvar') or initial.get('itemvar', '')
            if iv.startswith('q-'):
                q = self.instance.event.quotas.get(pk=iv[2:])
                choices.append(('q-%d' % q.pk, _('Any product in quota "{quota}"').format(quota=q)))
            elif '-' in iv:
                itemid, varid = iv.split('-')
                i = self.instance.event.items.get(pk=itemid)
                v = i.variations.get(pk=varid)
                choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (str(i), v.value)))
            elif iv:
                i = self.instance.event.items.get(pk=iv)
                if i.variations.exists():
                    choices.append((str(i.pk), _('{product} – Any variation').format(product=i)))
                else:
                    choices.append((str(i.pk), str(i)))

        self.fields['itemvar'].choices = choices
        self.fields['itemvar'].widget = Select2ItemVarQuota(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.vouchers.itemselect2', kwargs={
                    'event': instance.event.slug,
                    'organizer': instance.event.organizer.slug,
                }),
                'data-placeholder': ''
            }
        )
        self.fields['itemvar'].widget.choices = self.fields['itemvar'].choices
        self.fields['itemvar'].required = True

    def clean(self):
        data = super().clean()

        if not self._errors:
            try:
                itemid = quotaid = None
                iv = self.data.get('itemvar', '')
                if iv.startswith('q-'):
                    quotaid = iv[2:]
                elif '-' in iv:
                    itemid, varid = iv.split('-')
                else:
                    itemid, varid = iv, None

                if itemid:
                    self.instance.item = self.instance.event.items.get(pk=itemid)
                    if varid:
                        self.instance.variation = self.instance.item.variations.get(pk=varid)
                    else:
                        self.instance.variation = None
                    self.instance.quota = None

                else:
                    self.instance.quota = self.instance.event.quotas.get(pk=quotaid)
                    self.instance.item = None
                    self.instance.variation = None
            except ObjectDoesNotExist:
                raise ValidationError(_("Invalid product selected."))

        if 'codes' in data:
            data['codes'] = [a.strip() for a in data.get('codes', '').strip().split("\n") if a]
            cnt = len(data['codes']) * data.get('max_usages', 0)
        else:
            cnt = data.get('max_usages', 0)

        Voucher.clean_item_properties(
            data, self.instance.event,
            self.instance.quota, self.instance.item, self.instance.variation
        )
        if self.instance.quota:
            if all(i.hide_without_voucher for i in self.instance.quota.items.all()):
                raise ValidationError({
                    'itemvar': [
                        _('The quota you selected only contains hidden products. Hidden products can currently only be '
                          'shown by using vouchers that directly apply to the product, not via a quota.')
                    ]
                })
        Voucher.clean_subevent(
            data, self.instance.event
        )
        Voucher.clean_max_usages(data, self.instance.redeemed)
        check_quota = Voucher.clean_quota_needs_checking(
            data, self.initial_instance_data,
            item_changed=data.get('itemvar') != self.initial.get('itemvar'),
            creating=not self.instance.pk
        )
        if check_quota:
            Voucher.clean_quota_check(
                data, cnt, self.initial_instance_data, self.instance.event,
                self.instance.quota, self.instance.item, self.instance.variation
            )
        Voucher.clean_voucher_code(data, self.instance.event, self.instance.pk)

        voucher_form_validation.send(sender=self.instance.event, form=self, data=data)

        return data

    def save(self, commit=True):
        super().save(commit)

        return ['item']


class VoucherBulkForm(VoucherForm):
    codes = forms.CharField(
        widget=forms.Textarea,
        label=_("Codes"),
        help_text=_(
            "Add one voucher code per line. We suggest that you copy this list and save it into a file."
        ),
        required=True
    )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag', 'comment',
            'max_usages', 'price_mode', 'subevent', 'show_hidden_items'
        ]
        field_classes = {
            'valid_until': SplitDateTimeField,
            'subevent': SafeModelChoiceField,
        }
        widgets = {
            'valid_until': SplitDateTimePickerWidget(),
        }
        labels = {
            'max_usages': _('Maximum usages per voucher')
        }
        help_texts = {
            'max_usages': _('Number of times times EACH of these vouchers can be redeemed.')
        }

    def clean(self):
        data = super().clean()

        vouchers = self.instance.event.vouchers.annotate(
            code_lower=Lower('code')
        ).filter(code_lower__in=[c.lower() for c in data['codes']])
        if vouchers.exists():
            raise ValidationError(_('A voucher with one of these codes already exists.'))

        return data

    def save(self, event, *args, **kwargs):
        objs = []
        for code in self.cleaned_data['codes']:
            obj = modelcopy(self.instance)
            obj.event = event
            obj.code = code
            data = dict(self.cleaned_data)
            data['code'] = code
            data['bulk'] = True
            del data['codes']
            objs.append(obj)
        Voucher.objects.bulk_create(objs)
        return objs
