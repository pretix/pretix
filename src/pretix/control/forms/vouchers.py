import copy

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, ItemVariation, Quota, Voucher
from pretix.base.models.vouchers import _generate_random_code


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
            'code', 'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag',
            'comment', 'max_usages', 'price_mode'
        ]
        widgets = {
            'valid_until': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
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
            else:
                self.instance.variation = None
            self.instance.quota = None
        else:
            self.instance.quota = Quota.objects.get(pk=quotaid, event=self.instance.event)
            self.instance.item = None
            self.instance.variation = None

        if data['max_usages'] < self.instance.redeemed:
            raise ValidationError(
                _('This voucher has already been redeemed %(redeemed)s times. You cannot reduce the maximum number of '
                  'usages below this number.'),
                params={
                    'redeemed': self.instance.redeemed
                }
            )

        if 'number' in data:
            cnt = data['number'] * data['max_usages']
        else:
            cnt = data['max_usages']

        if self._clean_quota_needs_checking(data):
            self._clean_quota_check(data, cnt)

        if 'code' in data and Voucher.objects.filter(Q(code=data['code']) & Q(event=self.instance.event) & ~Q(pk=self.instance.pk)).exists():
            raise ValidationError(_('A voucher with this code already exists.'))

        return data

    def _clean_quota_needs_checking(self, data):
        # We only need to check for quota on vouchers that are now blocking quota and haven't
        # before (or have blocked a different quota before)
        if data.get('block_quota', False):
            is_valid = data.get('valid_until') is None or data.get('valid_until') >= now()
            if not is_valid:
                # If the voucher is not valid, it won't block any quota
                return False

            if not self.instance.pk:
                # This is a new voucher
                return True

            if not self.initial_instance_data.block_quota:
                # Change from nonblocking to blocking
                return True

            if not self._clean_was_valid():
                # This voucher has been expired and is now valid again and therefore blocks quota again
                return True

            if data.get('itemvar') != self.initial.get('itemvar'):
                # The voucher has been reassigned to a different item, variation or quota
                return True

        return False

    def _clean_was_valid(self):
        return self.initial_instance_data.valid_until is None or self.initial_instance_data.valid_until >= now()

    def _clean_quota_get_ignored(self):
        quotas = set()
        if self.initial_instance_data and self.initial_instance_data.block_quota and self._clean_was_valid():
            if self.initial_instance_data.quota:
                quotas.add(self.initial_instance_data.quota)
            elif self.initial_instance_data.variation:
                quotas |= set(self.initial_instance_data.variation.quotas.all())
            elif self.initial_instance_data.item:
                quotas |= set(self.initial_instance_data.item.quotas.all())
        return quotas

    def _clean_quota_check(self, data, cnt):
        old_quotas = self._clean_quota_get_ignored()

        if self.instance.quota:
            if self.instance.quota in old_quotas:
                return
            else:
                avail = self.instance.quota.availability()
        elif self.instance.item.has_variations and not self.instance.variation:
            raise ValidationError(_('You can only block quota if you specify a specific product variation. '
                                    'Otherwise it might be unclear which quotas to block.'))
        elif self.instance.item and self.instance.variation:
            avail = self.instance.variation.check_quotas(ignored_quotas=old_quotas)
        elif self.instance.item and not self.instance.item.has_variations:
            avail = self.instance.item.check_quotas(ignored_quotas=old_quotas)
        else:
            raise ValidationError(_('You need to specify either a quota or a product.'))

        if avail[0] != Quota.AVAILABILITY_OK or (avail[1] is not None and avail[1] < cnt):
            raise ValidationError(_('You cannot create a voucher that blocks quota as the selected product or '
                                    'quota is currently sold out or completely reserved.'))

    def save(self, commit=True):
        super().save(commit)

        return ['item']


class VoucherBulkForm(VoucherForm):
    number = forms.IntegerField(
        label=_("Number"),
        required=True
    )
    itemvar = forms.ChoiceField(
        label=_("Product"),
        widget=forms.RadioSelect
    )
    price_mode = forms.ChoiceField(
        choices=Voucher.PRICE_MODES,
    )
    has_valid_until = forms.BooleanField()
    value_percent = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2
    )
    value_subtract = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2
    )
    value_set = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2
    )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag', 'comment',
            'max_usages', 'price_mode'
        ]
        widgets = {
            'valid_until': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
        }
        labels = {
            'max_usages': _('Maximum usages per voucher')
        }
        help_texts = {
            'max_usages': _('Number of times times EACH of these vouchers can be redeemed.')
        }

    def clean(self):
        data = super().clean()

        if data.get('has_valid_until', False) and not data.get('valid_until'):
            raise ValidationError(_('You did not specify an expiration date for the vouchers.'))

        if data.get('price_mode', 'none') != 'none':
            if data.get('value_%s' % data['price_mode']) is None:
                raise ValidationError(_('You specified that the vouchers should modify the products price '
                                        'but did not specify a value.'))

        return data

    def save(self, event, *args, **kwargs):
        objs = []

        codes = set()
        while len(codes) < self.cleaned_data['number']:
            new_codes = set()
            for i in range(min(self.cleaned_data['number'] - len(codes), 500)):
                # Work around SQLite's SQLITE_MAX_VARIABLE_NUMBER
                new_codes.add(_generate_random_code())
            new_codes -= set([v['code'] for v in Voucher.objects.filter(code__in=new_codes).values('code')])
            codes |= new_codes

        for code in codes:
            obj = copy.copy(self.instance)
            obj.event = event
            obj.code = code
            data = dict(self.cleaned_data)
            data['code'] = code
            data['bulk'] = True
            obj.save()
            objs.append(obj)
        return objs
