from django import forms
from django.utils.translation import gettext_lazy as _

from pretix.base.services.orderimport import get_all_columns


class ProcessForm(forms.Form):
    orders = forms.ChoiceField(
        label=_('Import mode'),
        choices=(
            ('many', _('Create a separate order for each line')),
            ('one', _('Create one order with one position per line')),
        )
    )
    status = forms.ChoiceField(
        label=_('Order status'),
        choices=(
            ('paid', _('Create orders as fully paid')),
            ('pending', _('Create orders as pending and still require payment')),
        )
    )
    testmode = forms.BooleanField(
        label=_('Create orders as test mode orders'),
        required=False
    )

    def __init__(self, *args, **kwargs):
        headers = kwargs.pop('headers')
        initital = kwargs.pop('initial', {})
        self.event = kwargs.pop('event')
        initital['testmode'] = self.event.testmode
        kwargs['initial'] = initital
        super().__init__(*args, **kwargs)

        header_choices = [
            ('csv:{}'.format(h), _('CSV column: "{name}"').format(name=h)) for h in headers
        ]

        for c in get_all_columns(self.event):
            choices = []
            if c.default_value:
                choices.append((c.default_value, c.default_label))
            choices += header_choices
            for k, v in c.static_choices():
                choices.append(('static:{}'.format(k), v))

            self.fields[c.identifier] = forms.ChoiceField(
                label=str(c.verbose_name),
                choices=choices,
                widget=forms.Select(
                    attrs={'data-static': 'true'}
                )
            )
