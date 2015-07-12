from django import forms
from django.utils.translation import ugettext_lazy as _
from pretix.base.i18n import I18nFormField, I18nTextarea, I18nTextInput
from pretix.base.models import Order


class MailForm(forms.Form):
    sendto = forms.MultipleChoiceField(
        label=_("Send to"), widget=forms.CheckboxSelectMultiple,
        choices=Order.STATUS_CHOICE
    )
    subject = forms.CharField(label=_("Subject"))
    message = forms.CharField(label=_("Message"))

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['subject'] = I18nFormField(
            widget=I18nTextInput, required=True,
            langcodes=event.settings.get('locales')
        )
        self.fields['message'] = I18nFormField(
            widget=I18nTextarea, required=True,
            langcodes=event.settings.get('locales')
        )
