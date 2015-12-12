from pretix.base.forms import I18nModelForm
from pretix.base.models import Order


class ExtendForm(I18nModelForm):
    class Meta:
        model = Order
        fields = ['expires']
