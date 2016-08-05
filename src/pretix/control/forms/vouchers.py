import copy

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, ItemVariation, Quota, Voucher


class VoucherForm(I18nModelForm):
    itemvar = forms.ChoiceField(
        label=_("Product"),
        help_text=_(
            "This product is added to the user's cart if the voucher is redeemed."
        )
    )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'code', 'valid_until', 'block_quota', 'allow_ignore_quota', 'price', 'tag',
            'comment'
        ]

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        initial = kwargs.get('initial')
        if instance:
            try:
                if instance.variation:
                    initial['itemvar'] = '%d-%d' % (instance.item.pk, instance.variation.pk)
                elif instance.item:
                    initial['itemvar'] = str(instance.item.pk)
                elif instance.quota:
                    initial['itemvar'] = 'q-%d' % instance.quota.pk
            except Item.DoesNotExist:
                pass
        super().__init__(*args, **kwargs)
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
        itemid = quotaid = None
        if self.data['itemvar'].startswith('q-'):
            quotaid = self.data['itemvar'][2:]
        elif '-' in self.data['itemvar']:
            itemid, varid = self.data['itemvar'].split('-')
        else:
            itemid, varid = self.data['itemvar'], None

        if itemid:
            self.instance.item = Item.objects.get(pk=itemid, event=self.instance.event)
            if varid:
                self.instance.variation = ItemVariation.objects.get(pk=varid, item=self.instance.item)
                avail = self.instance.variation.check_quotas()
            else:
                self.instance.variation = None
                avail = self.instance.item.check_quotas()
            self.instance.quota = None
        else:
            self.instance.quota = Quota.objects.get(pk=quotaid, event=self.instance.event)
            self.instance.item = None
            self.instance.variation = None
            avail = self.instance.quota.availability()

        if 'codes' in data:
            data['codes'] = [a.strip() for a in data.get('codes', '').strip().split("\n") if a]
            cnt = len(data['codes'])
        else:
            cnt = 1

        if data.get('block_quota', False):
            if avail[0] != Quota.AVAILABILITY_OK or (avail[1] is not None and avail[1] < cnt):
                raise ValidationError(_('You cannot create a voucher that blocks quota as the selected product or quota is '
                                        'currently sold out or completely reserved.'))

            if 'code' in data and not self.instance.pk and Voucher.objects.filter(code=data['code'], event=self.instance.event).exists():
                raise ValidationError(_('A voucher with this code already exists.'))

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
            'valid_until', 'block_quota', 'allow_ignore_quota', 'price', 'tag', 'comment'
        ]

    def clean(self):
        data = super().clean()

        if Voucher.objects.filter(code__in=data['codes'], event=self.instance.event).exists():
            raise ValidationError(_('A voucher with one of this codes already exists.'))

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
            obj.save()
            objs.append(obj)
        return objs
