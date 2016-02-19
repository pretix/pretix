from pretix.base.forms import I18nModelForm
from pretix.base.models import Voucher


class VoucherForm(I18nModelForm):
    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'code', 'valid_until', 'block_quota', 'allow_ignore_quota', 'price', 'item'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = self.instance.event.items.all()

    def _get_validation_exclusions(self):
        return []
