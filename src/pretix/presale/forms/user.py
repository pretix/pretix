from django import forms
from django.utils.translation import gettext_lazy as _


class ResendLinkForm(forms.Form):
    email = forms.EmailField(label=_('E-mail'))
