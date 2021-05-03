from django.conf import settings
from django.contrib.auth.hashers import (
    check_password, is_password_usable, make_password,
)
from django.db import models
from django.utils.crypto import get_random_string, salted_hmac
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager, scopes_disabled
from jsonfallback.fields import FallbackJSONField

from pretix.base.banlist import banned
from pretix.base.models.base import LoggedModel
from pretix.base.models.organizer import Organizer
from pretix.base.settings import PERSON_NAME_SCHEMES


class Customer(LoggedModel):
    """
    Represents a registered customer of an organizer.
    """
    id = models.BigAutoField(primary_key=True)
    organizer = models.ForeignKey(Organizer, related_name='customers', on_delete=models.CASCADE)
    identifier = models.CharField(max_length=190, db_index=True, unique=True)
    email = models.EmailField(unique=True, db_index=True, null=True, blank=True,
                              verbose_name=_('E-mail'), max_length=190)
    password = models.CharField(verbose_name=_('Password'), max_length=128)
    name_cached = models.CharField(max_length=255, verbose_name=_('Full name'), blank=True)
    name_parts = FallbackJSONField(default=dict)
    is_active = models.BooleanField(default=True, verbose_name=_('Is active'))
    is_verified = models.BooleanField(default=True, verbose_name=_('Email verified'))
    last_login = models.DateTimeField(verbose_name=_('Last login'), blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name=_('Registration date'))
    locale = models.CharField(max_length=50,
                              choices=settings.LANGUAGES,
                              default=settings.LANGUAGE_CODE,
                              verbose_name=_('Language'))
    last_modified = models.DateTimeField(auto_now=True)

    objects = ScopedManager(organizer='organizer')

    class Meta:
        unique_together = [['organizer', 'email']]

    def save(self, **kwargs):
        self.email = self.email.lower()
        if 'update_fields' in kwargs and 'last_modified' not in kwargs['update_fields']:
            kwargs['update_fields'] = list(kwargs['update_fields']) + ['last_modified']
        if not self.identifier:
            self.assign_identifier()
        if self.name_parts:
            self.name_cached = self.name
        else:
            self.name_cached = ""
            self.name_parts = {}
        super().save(**kwargs)

    @scopes_disabled()
    def assign_identifier(self):
        charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        iteration = 0
        length = settings.ENTROPY['customer_identifier']
        while True:
            code = get_random_string(length=length, allowed_chars=charset)
            iteration += 1

            if banned(code):
                continue

            if not Customer.objects.filter(identifier=code).exists():
                self.identifier = code
                return

            if iteration > 20:
                # Safeguard: If we don't find an unused and non-banlisted code within 20 iterations, we increase
                # the length.
                length += 1
                iteration = 0

    @property
    def name(self):
        if not self.name_parts:
            return ""
        if '_legacy' in self.name_parts:
            return self.name_parts['_legacy']
        if '_scheme' in self.name_parts:
            scheme = PERSON_NAME_SCHEMES[self.name_parts['_scheme']]
        else:
            raise TypeError("Invalid name given.")
        return scheme['concatenation'](self.name_parts).strip()

    def __str__(self):
        return self.name or self.email

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """
        Return a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """
        def setter(raw_password):
            self.set_password(raw_password)
            self.save(update_fields=["password"])
        return check_password(raw_password, self.password, setter)

    def set_unusable_password(self):
        # Set a value that will never be a valid hash
        self.password = make_password(None)

    def has_usable_password(self):
        """
        Return False if set_unusable_password() has been called for this user.
        """
        return is_password_usable(self.password)

    def get_session_auth_hash(self):
        """
        Return an HMAC of the password field.
        """
        key_salt = "pretix.base.models.customers.Customer.get_session_auth_hash"
        payload = self.password
        payload += self.email
        return salted_hmac(key_salt, payload).hexdigest()

    def get_email_context(self):
        ctx = {
            'name': self.name,
            'organizer': self.organizer.name,
        }
        name_scheme = PERSON_NAME_SCHEMES[self.organizer.settings.name_scheme]
        for f, l, w in name_scheme['fields']:
            if f == 'full_name':
                continue
            ctx['name_%s' % f] = self.name_parts.get(f, '')
        return ctx
