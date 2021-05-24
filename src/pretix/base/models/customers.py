#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import pycountry
from django.conf import settings
from django.contrib.auth.hashers import (
    check_password, is_password_usable, make_password,
)
from django.db import models
from django.utils.crypto import get_random_string, salted_hmac
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager, scopes_disabled

from pretix.base.banlist import banned
from pretix.base.models.base import LoggedModel
from pretix.base.models.organizer import Organizer
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.helpers.countries import FastCountryField


class Customer(LoggedModel):
    """
    Represents a registered customer of an organizer.
    """
    id = models.BigAutoField(primary_key=True)
    organizer = models.ForeignKey(Organizer, related_name='customers', on_delete=models.CASCADE)
    identifier = models.CharField(max_length=190, db_index=True, unique=True)
    email = models.EmailField(db_index=True, null=True, blank=False, verbose_name=_('E-mail'), max_length=190)
    password = models.CharField(verbose_name=_('Password'), max_length=128)
    name_cached = models.CharField(max_length=255, verbose_name=_('Full name'), blank=True)
    name_parts = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True, verbose_name=_('Account active'))
    is_verified = models.BooleanField(default=True, verbose_name=_('Verified email address'))
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
        ordering = ('email',)

    def get_email_field_name(self):
        return 'email'

    def save(self, **kwargs):
        if self.email:
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

    def anonymize(self):
        self.is_active = False
        self.is_verified = False
        self.name_parts = {}
        self.name_cached = ''
        self.email = None
        self.save()
        self.all_logentries().update(data={}, shredded=True)
        self.orders.all().update(customer=None)
        self.memberships.all().update(attendee_name_parts=None)
        self.attendee_profiles.all().delete()
        self.invoice_addresses.all().delete()

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
        s = f'#{self.identifier}'
        if self.name or self.email:
            s += f' – {self.name or self.email}'
        if not self.is_active:
            s += f' ({_("disabled")})'
        return s

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

    @property
    def stored_addresses(self):
        return self.invoice_addresses(manager='profiles')


class AttendeeProfile(models.Model):
    customer = models.ForeignKey(
        Customer,
        related_name='attendee_profiles',
        on_delete=models.CASCADE
    )
    attendee_name_cached = models.CharField(
        max_length=255,
        verbose_name=_("Attendee name"),
        blank=True, null=True,
    )
    attendee_name_parts = models.JSONField(
        blank=True, default=dict
    )
    attendee_email = models.EmailField(
        verbose_name=_("Attendee email"),
        blank=True, null=True,
    )
    company = models.CharField(max_length=255, blank=True, verbose_name=_('Company name'), null=True)
    street = models.TextField(verbose_name=_('Address'), blank=True, null=True)
    zipcode = models.CharField(max_length=30, verbose_name=_('ZIP code'), blank=True, null=True)
    city = models.CharField(max_length=255, verbose_name=_('City'), blank=True, null=True)
    country = FastCountryField(verbose_name=_('Country'), blank=True, blank_label=_('Select country'), null=True)
    state = models.CharField(max_length=255, verbose_name=pgettext_lazy('address', 'State'), blank=True, null=True)
    answers = models.JSONField(default=list)

    objects = ScopedManager(organizer='customer__organizer')

    @property
    def attendee_name(self):
        if not self.attendee_name_parts:
            return None
        if '_legacy' in self.attendee_name_parts:
            return self.attendee_name_parts['_legacy']
        if '_scheme' in self.attendee_name_parts:
            scheme = PERSON_NAME_SCHEMES[self.attendee_name_parts['_scheme']]
        else:
            scheme = PERSON_NAME_SCHEMES[self.customer.organizer.settings.name_scheme]
        return scheme['concatenation'](self.attendee_name_parts).strip()

    @property
    def state_name(self):
        sd = pycountry.subdivisions.get(code='{}-{}'.format(self.country, self.state))
        if sd:
            return sd.name
        return self.state

    @property
    def state_for_address(self):
        from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS
        if not self.state or str(self.country) not in COUNTRIES_WITH_STATE_IN_ADDRESS:
            return ""
        if COUNTRIES_WITH_STATE_IN_ADDRESS[str(self.country)][1] == 'long':
            return self.state_name
        return self.state

    def describe(self):
        from .items import Question
        from .orders import QuestionAnswer

        parts = [
            self.attendee_name,
            self.attendee_email,
            self.company,
            self.street,
            (self.zipcode or '') + ' ' + (self.city or '') + ' ' + (self.state_for_address or ''),
            self.country.name,
        ]
        for a in self.answers:
            val = str(QuestionAnswer(question=Question(type=a.get('question_type')), answer=str(a.get('value'))))
            parts.append(f'{a["field_label"]}: {val}')

        return '\n'.join([str(p).strip() for p in parts if p and str(p).strip()])
