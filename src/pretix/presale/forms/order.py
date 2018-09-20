from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from pretix.base.validators import EmailBlacklistValidator


class ChangeContactForm(forms.Form):
    email = forms.EmailField(label=_('E-mail'),
                             help_text=_('Make sure to enter a valid email address. We will send an email containing '
                                         'the new link to the ticket there.'),
                             validators=[EmailBlacklistValidator()])
    email_repeat = forms.EmailField(
        label=_('E-mail address (repeated)'),
        help_text=_('Please enter the same email address again to make sure you typed it correctly.')
    )
    check_noaccess = forms.BooleanField(
        label=_('I have understood that after this operation, I will no longer have access to these tickets. The link '
                'of the ticket order will be changed and the new link will be sent to the given email address.')
    )
    check_printed = forms.BooleanField(
        label=_('I have understood that after this operation, all printed or downloaded tickets from this order will '
                'be invalid and need to be downloaded again.')
    )
    check_data = forms.BooleanField(
        label=_('I have understood that after this operation, the new owner will have access to all personal data '
                'included in my ticket order, such as information given for the tickets, my invoicing address, or '
                'previous invoices.')
    )

    def clean(self):
        if self.cleaned_data.get('email').lower() != self.cleaned_data.get('email_repeat').lower():
            raise ValidationError(_('Please enter the same email address twice.'))
