from django import forms
from django.urls import reverse
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput

from pretix.base.forms import PlaceholderValidator
from pretix.base.models import Item, Order, SubEvent
from pretix.control.forms.widgets import Select2


class MailForm(forms.Form):
    sendto = forms.MultipleChoiceField()  # overridden later
    subject = forms.CharField(label=_("Subject"))
    message = forms.CharField(label=_("Message"))
    items = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'scrolling-multiple-choice'}
        ),
        label=_('Only send to people who bought'),
        required=True,
        queryset=Item.objects.none()
    )
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
            label=_('Subject'),
            widget=I18nTextInput, required=True,
            locales=event.settings.get('locales'),
            help_text=_("Available placeholders: {expire_date}, {event}, {code}, {date}, {url}, "
                        "{invoice_name}, {invoice_company}"),
            validators=[PlaceholderValidator(['{expire_date}', '{event}', '{code}', '{date}', '{url}',
                                              '{invoice_name}', '{invoice_company}'])]
        )
        self.fields['message'] = I18nFormField(
            label=_('Message'),
            widget=I18nTextarea, required=True,
            locales=event.settings.get('locales'),
            help_text=_("Available placeholders: {expire_date}, {event}, {code}, {date}, {url}, "
                        "{invoice_name}, {invoice_company}"),
            validators=[PlaceholderValidator(['{expire_date}', '{event}', '{code}', '{date}', '{url}',
                                              '{invoice_name}', '{invoice_company}'])]
        )
        choices = list(Order.STATUS_CHOICE)
        if not event.settings.get('payment_term_expire_automatically', as_type=bool):
            choices.append(
                ('overdue', _('pending with payment overdue'))
            )
        self.fields['sendto'] = forms.MultipleChoiceField(
            label=_("Send to customers with order status"),
            widget=forms.CheckboxSelectMultiple(
                attrs={'class': 'scrolling-multiple-choice'}
            ),
            choices=choices
        )
        if not self.initial.get('sendto'):
            self.initial['sendto'] = ['p', 'n']

        self.fields['items'].queryset = event.items.all()
        if not self.initial.get('items'):
            self.initial['items'] = event.items.all()

        if event.has_subevents:
            self.fields['subevent'].queryset = event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'Date')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        else:
            del self.fields['subevent']
