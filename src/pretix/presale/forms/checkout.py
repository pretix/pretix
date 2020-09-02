from itertools import chain

import dns
from django import forms
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.phonenumber import PhoneNumber
from phonenumbers import NumberParseException
from phonenumbers.data import _COUNTRY_CODE_TO_REGION_CODE

from pretix.base.forms.questions import (
    BaseInvoiceAddressForm, BaseQuestionsForm, WrappedPhoneNumberPrefixWidget,
    guess_country,
)
from pretix.base.i18n import get_babel_locale, language
from pretix.base.validators import EmailBanlistValidator
from pretix.presale.signals import contact_form_fields


class EmailDNSValidator():
    def __call__(self, value):
        domain = value.split('@')[-1]
        works = cache.get(f"mail_domain_exists_{domain}")
        if works:
            return value

        resolver = dns.resolver.Resolver()
        resolver.lifetime = 0.5
        resolver.timeout = 0.5
        record_types = ('MX', 'AAAA', 'A')
        for record_type in record_types:
            try:
                if len(resolver.query(domain, record_type)):
                    cache.set(f"mail_domain_exists_{domain}", "true", 3600 * 24 * 7)
                    return value
            except:
                continue
        raise ValidationError(
            _('Please check your email domain, it does not look like "%(value)s" is able to receive emails.'),
            code='dns',
            params={'value': domain},
        )


class ContactForm(forms.Form):
    required_css_class = 'required'
    email = forms.EmailField(
        label=_('E-mail'),
        validators=[
            EmailBanlistValidator(),
            EmailDNSValidator(),
        ],
        widget=forms.EmailInput(attrs={'autocomplete': 'section-contact email'})
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.request = kwargs.pop('request')
        self.all_optional = kwargs.pop('all_optional', False)
        super().__init__(*args, **kwargs)

        if self.event.settings.order_email_asked_twice:
            self.fields['email_repeat'] = forms.EmailField(
                label=_('E-mail address (repeated)'),
                help_text=_('Please enter the same email address again to make sure you typed it correctly.'),
            )

        if self.event.settings.order_phone_asked:
            with language(get_babel_locale()):
                default_country = guess_country(self.event)
                default_prefix = None
                for prefix, values in _COUNTRY_CODE_TO_REGION_CODE.items():
                    if str(default_country) in values:
                        default_prefix = prefix
                try:
                    initial = self.initial.pop('phone', None)
                    initial = PhoneNumber().from_string(initial) if initial else "+{}.".format(default_prefix)
                except NumberParseException:
                    initial = None
                self.fields['phone'] = PhoneNumberField(
                    label=_('Phone number'),
                    required=self.event.settings.order_phone_required,
                    help_text=self.event.settings.checkout_phone_helptext,
                    # We now exploit an implementation detail in PhoneNumberPrefixWidget to allow us to pass just
                    # a country code but no number as an initial value. It's a bit hacky, but should be stable for
                    # the future.
                    initial=initial,
                    widget=WrappedPhoneNumberPrefixWidget()
                )

        if not self.request.session.get('iframe_session', False):
            # There is a browser quirk in Chrome that leads to incorrect initial scrolling in iframes if there
            # is an autofocus field. Who would have thought… See e.g. here:
            # https://floatboxjs.com/forum/topic.php?post=8440&usebb_sid=2e116486a9ec6b7070e045aea8cded5b#post8440
            self.fields['email'].widget.attrs['autofocus'] = 'autofocus'
        self.fields['email'].help_text = self.event.settings.checkout_email_helptext

        responses = contact_form_fields.send(self.event, request=self.request)
        for r, response in responses:
            for key, value in response.items():
                # We need to be this explicit, since OrderedDict.update does not retain ordering
                self.fields[key] = value
        if self.all_optional:
            for k, v in self.fields.items():
                v.required = False
                v.widget.is_required = False

    def clean(self):
        if self.event.settings.order_email_asked_twice and self.cleaned_data.get('email') and self.cleaned_data.get('email_repeat'):
            if self.cleaned_data.get('email').lower() != self.cleaned_data.get('email_repeat').lower():
                raise ValidationError(_('Please enter the same email address twice.'))


class InvoiceAddressForm(BaseInvoiceAddressForm):
    required_css_class = 'required'
    vat_warning = True


class InvoiceNameForm(InvoiceAddressForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in list(self.fields.keys()):
            if f != 'name_parts':
                del self.fields[f]


class QuestionsForm(BaseQuestionsForm):
    """
    This form class is responsible for asking order-related questions. This includes
    the attendee name for admission tickets, if the corresponding setting is enabled,
    as well as additional questions defined by the organizer.
    """
    required_css_class = 'required'


class AddOnRadioSelect(forms.RadioSelect):
    option_template_name = 'pretixpresale/forms/addon_choice_option.html'

    def optgroups(self, name, value, attrs=None):
        attrs = attrs or {}
        groups = []
        has_selected = False
        for index, (option_value, option_label, option_desc) in enumerate(chain(self.choices)):
            if option_value is None:
                option_value = ''
            if isinstance(option_label, (list, tuple)):
                raise TypeError('Choice groups are not supported here')
            group_name = None
            subgroup = []
            groups.append((group_name, subgroup, index))

            selected = (
                force_str(option_value) in value and
                (has_selected is False or self.allow_multiple_selected)
            )
            if selected is True and has_selected is False:
                has_selected = True
            attrs['description'] = option_desc
            subgroup.append(self.create_option(
                name, option_value, option_label, selected, index,
                subindex=None, attrs=attrs,
            ))

        return groups


class AddOnVariationField(forms.ChoiceField):
    def valid_value(self, value):
        text_value = force_str(value)
        for k, v, d in self.choices:
            if value == k or text_value == force_str(k):
                return True
        return False
