import copy

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, ItemVariation, Quota, Voucher
from pretix.control.forms import SplitDateTimePickerWidget
from pretix.control.signals import voucher_form_validation


class VoucherForm(I18nModelForm):
    itemvar = forms.ChoiceField(
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
            'comment', 'max_usages', 'price_mode', 'subevent'
        ]
        field_classes = {
            'valid_until': forms.SplitDateTimeField,
        }
        widgets = {
            'valid_until': SplitDateTimePickerWidget(),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        initial = kwargs.get('initial')
        if instance:
            self.initial_instance_data = copy.copy(instance)
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
        elif 'subevent':
            del self.fields['subevent']

        choices = []
        for i in self.instance.event.items.prefetch_related('variations').all():
            variations = list(i.variations.all())
            if variations:
                choices.append((str(i.pk), _('{product} – Any variation').format(product=i.name)))
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (i.name, v.value)))
            else:
                choices.append((str(i.pk), i.name))
        for q in self.instance.event.quotas.all():
            choices.append(('q-%d' % q.pk, _('Any product in quota "{quota}"').format(quota=q)))
        self.fields['itemvar'].choices = choices

    def clean(self):
        data = super().clean()

        if not self._errors:
            itemid = quotaid = None
            iv = self.data.get('itemvar', '')
            if iv.startswith('q-'):
                quotaid = iv[2:]
            elif '-' in iv:
                itemid, varid = iv.split('-')
            else:
                itemid, varid = iv, None

            if itemid:
                self.instance.item = Item.objects.get(pk=itemid, event=self.instance.event)
                if varid:
                    self.instance.variation = ItemVariation.objects.get(pk=varid, item=self.instance.item)
                else:
                    self.instance.variation = None
                self.instance.quota = None

            else:
                self.instance.quota = Quota.objects.get(pk=quotaid, event=self.instance.event)
                self.instance.item = None
                self.instance.variation = None

        if 'codes' in data:
            data['codes'] = [a.strip() for a in data.get('codes', '').strip().split("\n") if a]
            cnt = len(data['codes']) * data['max_usages']
        else:
            cnt = data['max_usages']

        Voucher.clean_item_properties(
            data, self.instance.event,
            self.instance.quota, self.instance.item, self.instance.variation
        )
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
            'max_usages', 'price_mode', 'subevent'
        ]
        field_classes = {
            'valid_until': forms.SplitDateTimeField,
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

        if Voucher.objects.filter(code__in=data['codes'], event=self.instance.event).exists():
            raise ValidationError(_('A voucher with one of these codes already exists.'))

        return data

    def save(self, event, *args, **kwargs):
        objs = []
        for code in self.cleaned_data['codes']:
            obj = copy.copy(self.instance)
            obj.event = event
            obj.code = code
            data = dict(self.cleaned_data)
            data['code'] = code
            data['bulk'] = True
            del data['codes']
            objs.append(obj)
        Voucher.objects.bulk_create(objs)
        return objs
