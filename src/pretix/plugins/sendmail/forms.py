import re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import BaseValidator
from django.utils.translation import ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput

from pretix.base.models import Order


class PlaceholderValidator(BaseValidator):
    """
    Takes list of allowed placeholders,
    validates form field by checking for placeholders,
    which are not presented in taken list.
    """

    def __init__(self, limit_value):
        super().__init__(limit_value)
        self.limit_value = limit_value

    def __call__(self, value):
        data_placeholders = list(re.findall(r'({[\w\s]*})', str(value), re.X))

        invalid_placeholders = []
        for placeholder in data_placeholders:
            if placeholder not in self.limit_value:
                invalid_placeholders.append(placeholder)
        if invalid_placeholders:
            raise ValidationError(
                _('Invalid placeholder(s): %(value)s'),
                code='invalid',
                params={'value': ", ".join(invalid_placeholders)},
            )

    def clean(self, x):
        return x


class MailForm(forms.Form):
    sendto = forms.MultipleChoiceField()  # overridden later
    subject = forms.CharField(label=_("Subject"))
    message = forms.CharField(label=_("Message"))

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['subject'] = I18nFormField(
            widget=I18nTextInput, required=True,
            locales=event.settings.get('locales')
        )
        self.fields['message'] = I18nFormField(
            widget=I18nTextarea, required=True,
            locales=event.settings.get('locales'),
            help_text=_("Available placeholders: {due_date}, {event}, {order}, {order_date}, {order_url}, "
                        "{invoice_name}, {invoice_company}"),
            validators=[PlaceholderValidator(['{due_date}', '{event}', '{order}', '{order_date}', '{order_url}',
                                              '{invoice_name}', '{invoice_company}'])]
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
