from django import forms
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField
from phonenumbers.data import _COUNTRY_CODE_TO_REGION_CODE

from pretix.base.forms.questions import (
    NamePartsFormField, WrappedPhoneNumberPrefixWidget, guess_country,
)
from pretix.base.i18n import get_babel_locale, language
from pretix.base.models import WaitingListEntry


class WaitingListForm(forms.ModelForm):
    required_css_class = 'required'

    class Meta:
        model = WaitingListEntry
        fields = ('name_parts', 'email', 'phone')

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        event = self.event

        if event.settings.waiting_list_names_asked:
            self.fields['name_parts'] = NamePartsFormField(
                max_length=255,
                required=event.settings.waiting_list_names_required,
                scheme=event.settings.name_scheme,
                titles=event.settings.name_scheme_titles,
                label=_('Name'),
            )
        else:
            del self.fields['name_parts']

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
        else:
            del self.fields['phone']
