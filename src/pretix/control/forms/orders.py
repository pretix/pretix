from pretix.base.forms import VersionedModelForm

from pretix.base.models import Order


class ExtendForm(VersionedModelForm):
    class Meta:
        model = Order
        fields = ['expires']
