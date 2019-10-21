from django import forms
from django.urls import reverse
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput

from pretix.base.email import get_available_placeholders
from pretix.base.forms import PlaceholderValidator
from pretix.base.models import CheckinList, Item, Order, SubEvent
from pretix.control.forms.widgets import Select2, Select2Multiple


class MailForm(forms.Form):
    recipients = forms.ChoiceField(
        label=_('Send email to'),
        widget=forms.RadioSelect,
        initial='orders',
        choices=[]
    )
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
    filter_checkins = forms.BooleanField(
        label=_('Filter check-in status'),
        required=False
    )
    checkin_lists = SafeModelMultipleChoiceField(queryset=CheckinList.objects.none(), required=False)  # overridden later
    not_checked_in = forms.BooleanField(label=_("Send to customers not checked in"), required=False)
    subevent = forms.ModelChoiceField(
        SubEvent.objects.none(),
        label=_('Only send to customers of'),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )

    def _set_field_placeholders(self, fn, base_parameters):
        phs = [
            '{%s}' % p
            for p in sorted(get_available_placeholders(self.event, base_parameters).keys())
        ]
        ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(phs)
        )

    def __init__(self, *args, **kwargs):
        event = self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        recp_choices = [
            ('orders', _('Everyone who created a ticket order'))
        ]
        if event.settings.attendee_emails_asked:
            recp_choices += [
                ('attendees', _('Every attendee (falling back to the order contact when no attendee email address is '
                                'given)')),
                ('both', _('Both (all order contact addresses and all attendee email addresses)'))
            ]
        self.fields['recipients'].choices = recp_choices

        self.fields['subject'] = I18nFormField(
            label=_('Subject'),
            widget=I18nTextInput, required=True,
            locales=event.settings.get('locales'),
        )
        self.fields['message'] = I18nFormField(
            label=_('Message'),
            widget=I18nTextarea, required=True,
            locales=event.settings.get('locales'),
        )
        self._set_field_placeholders('subject', ['event', 'order', 'position_or_address'])
        self._set_field_placeholders('message', ['event', 'order', 'position_or_address'])
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

        self.fields['checkin_lists'].queryset = event.checkin_lists.all()
        self.fields['checkin_lists'].widget = Select2Multiple(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.orders.checkinlists.select2', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                }),
                'data-placeholder': _('Send to customers checked in on list'),
                'data-inverse-dependency': '#id_not_checked_in'
            }
        )
        self.fields['checkin_lists'].widget.choices = self.fields['checkin_lists'].choices
        self.fields['checkin_lists'].label = _('Send to customers checked in on list')

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
