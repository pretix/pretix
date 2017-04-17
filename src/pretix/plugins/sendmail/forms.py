from django import forms
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput

from pretix.base.models import Order
from pretix.base.models.event import SubEvent
from pretix.plugins.sendmail.email import mail_text_sendmail


class MailForm(forms.Form):
    sendto = forms.MultipleChoiceField()  # overridden later
    subject = forms.CharField(label=_("Subject"))
    message = forms.CharField(label=_("Message"))
    subevent = forms.ModelChoiceField(
        SubEvent.objects.none(),
        label=_('Only send to customers of'),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['subject'] = I18nFormField(
            widget=I18nTextInput, required=True,
            locales=event.settings.get('locales')
        )
        self.fields['message'] = mail_text_sendmail.formfield(
            widget=I18nTextarea, required=True,
            locales=event.settings.get('locales'),
        )
        choices = list(Order.STATUS_CHOICE)
        if not event.settings.get('payment_term_expire_automatically', as_type=bool):
            choices.append(
                ('overdue', _('pending with payment overdue'))
            )
        self.fields['sendto'] = forms.MultipleChoiceField(
            label=_("Send to"), widget=forms.CheckboxSelectMultiple,
            choices=choices
        )
        if event.has_subevents:
            self.fields['subevent'].queryset = event.subevents.all()
        else:
            del self.fields['subevent']
