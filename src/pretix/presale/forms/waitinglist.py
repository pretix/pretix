from django import forms
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField
from phonenumbers.data import _COUNTRY_CODE_TO_REGION_CODE

from pretix.base.forms.questions import (
    guess_country, NamePartsFormField, WrappedPhoneNumberPrefixWidget
)
from pretix.base.i18n import (
    get_babel_locale, language,
)
from pretix.base.models import WaitingListEntry


class WaitingListForm(forms.ModelForm):
    class Meta:
        model = WaitingListEntry
        fields = ('email',)

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        field_order = []

        event = self.event

        if event.settings.waiting_list_names_asked:
            self.fields['name_parts'] = NamePartsFormField(
                max_length=255,
                required=event.settings.waiting_list_names_required,
                scheme=event.settings.name_scheme,
                titles=event.settings.name_scheme_titles,
                label=_('Name'),
            )
            field_order.append('name_parts')

        field_order.append('email')

        if event.settings.waiting_list_phones_asked:
            with language(get_babel_locale()):
                default_country = guess_country(self.event)
                default_prefix = None
                for prefix, values in _COUNTRY_CODE_TO_REGION_CODE.items():
                    if str(default_country) in values:
                        default_prefix = prefix

                self.fields['phone'] = PhoneNumberField(
                    label=_("Phone number"),
                    required=event.settings.waiting_list_phones_required,
                    help_text=event.settings.waiting_list_phones_explanation_text,
                    # We now exploit an implementation detail in PhoneNumberPrefixWidget to allow us to pass just
                    # a country code but no number as an initial value. It's a bit hacky, but should be stable for
                    # the future.
                    initial="+{}.".format(default_prefix) if default_prefix else None,
                    widget=WrappedPhoneNumberPrefixWidget()
                )
            field_order.append('phone')

        if len(field_order) > 1:
            self.order_fields(field_order)
