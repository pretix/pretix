from collections import OrderedDict
from importlib import import_module

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _


def get_auth_backends():
    backends = {}
    for b in settings.PRETIX_AUTH_BACKENDS:
        mod, name = b.rsplit('.', 1)
        b = getattr(import_module(mod), name)()
        backends[b.identifier] = b
    return backends


class BaseAuthBackend:
    @property
    def identifier(self):
        """
        A short and unique identifier for this authentication backend.
        This should only contain lowercase letters and in most cases will
        be the same as your package name.
        """
        raise NotImplementedError()

    @property
    def verbose_name(self):
        """
        A human-readable name of this authentication backend.
        """
        raise NotImplementedError()

    @property
    def visible(self):
        """
        Whether or not this backend can be selected by users actively.
        """
        return True

    @property
    def login_form_fields(self) -> dict:
        """
        This property may return form fields that the user needs to fill in
        to log in.
        """
        return {}

    def form_authenticate(self, request, form_data):
        """
        TODO
        :param request:
        :param form_data:
        :return:
        """
        return

    def request_authenticate(self, request):
        """
        TODO
        :param request:
        :param form_data:
        :return:
        """
        return

    def authentication_url(self, request):
        """
        TODO
        :param request:
        :param form_data:
        :return:
        """
        return


class NativeAuthBackend(BaseAuthBackend):
    identifier = 'native'
    verbose_name = _('pretix User')

    @property
    def login_form_fields(self) -> dict:
        """
        This property may return form fields that the user needs to fill in
        to log in.
        """
        d = OrderedDict([
            ('email', forms.EmailField(label=_("E-mail"), max_length=254,
                                       widget=forms.EmailInput(attrs={'autofocus': 'autofocus'}))),
            ('password', forms.CharField(label=_("Password"), widget=forms.PasswordInput)),
        ])
        return d

    def form_authenticate(self, request, form_data):
        return authenticate(request=request, email=form_data['email'].lower(), password=form_data['password'])
