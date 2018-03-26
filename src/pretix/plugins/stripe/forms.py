from django import forms
from django.utils.translation import ugettext_lazy as _


class StripeKeyValidator():
    def __init__(self, prefix):
        assert isinstance(prefix, str)
        assert len(prefix) > 0
        self._prefix = prefix

    def __call__(self, value):
        if not value.startswith(self._prefix):
            raise forms.ValidationError(
                _('The provided key "%(value)s" does not look valid. It should start with "%(prefix)s".'),
                code='invalid-stripe-secret-key',
                params={
                    'value': value,
                    'prefix': self._prefix,
                },
            )
