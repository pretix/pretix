from django import forms
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, ItemVariation, Voucher


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
            'code', 'valid_until', 'block_quota', 'allow_ignore_quota', 'price'
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
            except Item.DoesNotExist:
                pass
        super().__init__(*args, **kwargs)
        choices = []
        for i in self.instance.event.items.prefetch_related('variations').all():
            variations = list(i.variations.all())
            if variations:
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (i.name, v.value)))
            else:
                choices.append((str(i.pk), i.name))
        self.fields['itemvar'].choices = choices

    def save(self, commit=True):
        if '-' in self.cleaned_data['itemvar']:
            itemid, varid = self.cleaned_data['itemvar'].split('-')
        else:
            itemid, varid = self.cleaned_data['itemvar'], None
        self.instance.item = Item.objects.get(pk=itemid, event=self.instance.event)
        if varid:
            self.instance.variation = ItemVariation.objects.get(pk=varid, item=self.instance.item)
        else:
            self.instance.variation = None
        super().save(commit)

        return ['item']
