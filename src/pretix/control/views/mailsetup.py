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
import logging

import dns.resolver
from django.conf import settings
from django.contrib import messages
from django.core.mail import get_connection
from django.shortcuts import redirect
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from pretix.base import email
from pretix.base.forms import SECRET_REDACTED
from pretix.base.models import Event
from pretix.base.services.mail import mail
from pretix.control.forms.filter import OrganizerFilterForm
from pretix.control.forms.mailsetup import SimpleMailForm, SMTPMailForm

logger = logging.getLogger(__name__)


def get_spf_record(hostname):
    try:
        r = dns.resolver.Resolver()
        for resp in r.query(hostname, 'TXT'):
            data = b''.join(resp.strings).decode()
            if data.lower().strip().startswith('v=spf1 '):  # RFC7208, section 4.5
                return data
    except:
        logger.exception("Could not fetch SPF record")


def _check_spf_record(not_found_lookup_parts, spf_record, depth):
    if depth > 10:  # prevent infinite loops
        return

    parts = spf_record.lower().split(" ")  # RFC 7208, section 4.6.1

    for p in parts:
        try:
            not_found_lookup_parts.remove(p)
        except KeyError:
            pass

    if not not_found_lookup_parts:  # save some DNS requests if we already found everything
        return

    for p in parts:
        if p.startswith('include:') or p.startswith('+include:'):
            _, hostname = p.split(':')
            rec_record = get_spf_record(hostname)
            if rec_record:
                _check_spf_record(not_found_lookup_parts, rec_record, depth + 1)


def check_spf_record(lookup, spf_record):
    """
    Check that all parts of lookup appear somewhere in the given SPF record, resolving
    include: directives recursively
    """
    not_found_lookup_parts = set(lookup.split(" "))
    _check_spf_record(not_found_lookup_parts, spf_record, 0)
    return not not_found_lookup_parts


class MailSettingsSetupView(TemplateView):
    template_name = 'pretixcontrol/email_setup.html'
    basetpl = None

    @cached_property
    def object(self):
        return getattr(self.request, 'event', self.request.organizer)

    @cached_property
    def smtp_form(self):
        return SMTPMailForm(
            obj=self.object,
            prefix='smtp',
            data=self.request.POST if (self.request.method == "POST" and self.request.POST.get("mode") == "smtp") else None,
        )

    @cached_property
    def simple_form(self):
        return SimpleMailForm(
            obj=self.object,
            prefix='simple',
            data=self.request.POST if (self.request.method == "POST" and self.request.POST.get("mode") == "simple") else None,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['basetpl'] = self.basetpl
        ctx['object'] = self.object
        ctx['smtp_form'] = self.smtp_form
        ctx['simple_form'] = self.simple_form
        ctx['default_sender_address'] = settings.MAIL_FROM_ORGANIZERS
        if 'mode' in self.request.POST:
            ctx['mode'] = self.request.POST.get('mode')
        elif self.object.settings.smtp_use_custom:
            ctx['mode'] = 'smtp'
        elif self.object.settings.mail_from not in (settings.MAIL_FROM_ORGANIZERS, settings.MAIL_FROM):
            ctx['mode'] = 'simple'
        else:
            ctx['mode'] = 'system'
        return ctx

    @cached_property
    def filter_form(self):
        return OrganizerFilterForm(data=self.request.GET, request=self.request)

    def post(self, request, *args, **kwargs):
        if request.POST.get('mode') == 'system':
            if isinstance(self.object, Event) and 'mail_from' in self.object.organizer.settings._cache():
                self.object.settings.mail_from = settings.MAIL_FROM_ORGANIZERS
            else:
                del self.object.settings.mail_from
            self.object.settings.smtp_use_custom = False
            del self.object.settings.smtp_host
            del self.object.settings.smtp_port
            del self.object.settings.smtp_username
            del self.object.settings.smtp_password
            del self.object.settings.smtp_use_tls
            del self.object.settings.smtp_use_ssl
            messages.success(request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())

        elif request.POST.get('mode') == 'reset':
            del self.object.settings.mail_from
            del self.object.settings.smtp_use_custom
            del self.object.settings.smtp_host
            del self.object.settings.smtp_port
            del self.object.settings.smtp_username
            del self.object.settings.smtp_password
            del self.object.settings.smtp_use_tls
            del self.object.settings.smtp_use_ssl
            messages.success(request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())

        elif request.POST.get('mode') == 'simple':
            if not self.simple_form.is_valid():
                return super().get(request, *args, **kwargs)

            session_key = f'sender_mail_verification_code_{self.request.path}_{self.simple_form.cleaned_data.get("mail_from")}'
            allow_save = (
                (not settings.MAIL_CUSTOM_SENDER_VERIFICATION_REQUIRED or
                 ('verification' in self.request.POST and self.request.POST.get('verification', '') == self.request.session.get(session_key, None))) and
                (not settings.MAIL_CUSTOM_SENDER_SPF_STRING or self.request.POST.get('state') == 'save')
            )

            if allow_save:
                self.object.settings.smtp_use_custom = False
                del self.object.settings.smtp_host
                del self.object.settings.smtp_port
                del self.object.settings.smtp_username
                del self.object.settings.smtp_password
                del self.object.settings.smtp_use_tls
                del self.object.settings.smtp_use_ssl
                for k, v in self.simple_form.cleaned_data.items():
                    self.object.settings.set(k, v)
                self.log_action(self.simple_form.cleaned_data)
                if session_key in request.session:
                    del request.session[session_key]
                messages.success(request, _('Your changes have been saved.'))
                return redirect(self.get_success_url())

            spf_warning = None
            spf_record = None
            if settings.MAIL_CUSTOM_SENDER_SPF_STRING:
                hostname = self.simple_form.cleaned_data['mail_from'].split('@')[-1]
                spf_record = get_spf_record(hostname)
                if not spf_record:
                    spf_warning = _(
                        'We could not find an SPF record set for the domain you are trying to use. This means that '
                        'there is a very high change most of the emails will be rejected or marked as spam. We '
                        'strongly recommend setting an SPF record on the domain. You can do so through the DNS '
                        'settings at the provider you registered your domain with.'
                    )
                elif not check_spf_record(settings.MAIL_CUSTOM_SENDER_SPF_STRING, spf_record):
                    spf_warning = _(
                        'We found an SPF record set for the domain you are trying to use, but it does not include this '
                        'system\'s email server. This means that there is a very high chance most of the emails will be '
                        'rejected or marked as spam. You should update the DNS settings of your domain to include '
                        'this system in the SPF record.'
                    )

            verification = settings.MAIL_CUSTOM_SENDER_VERIFICATION_REQUIRED and not spf_warning
            if verification:
                if 'verification' in self.request.POST:
                    messages.error(request, _('The verification code was incorrect, please try again.'))
                else:
                    self.request.session[session_key] = get_random_string(length=6, allowed_chars='1234567890')
                    mail(
                        self.simple_form.cleaned_data.get('mail_from'),
                        _('Sender address verification'),
                        'pretixcontrol/email/email_setup.txt',
                        {
                            'code': self.request.session[session_key],
                            'address': self.simple_form.cleaned_data.get('mail_from'),
                            'instance': settings.PRETIX_INSTANCE_NAME,
                        },
                        None,
                        locale=self.request.LANGUAGE_CODE,
                        user=self.request.user
                    )

            return self.response_class(
                request=self.request,
                template='pretixcontrol/email_setup_simple.html',
                context={
                    'basetpl': self.basetpl,
                    'object': self.object,
                    'verification': verification,
                    'spf_warning': spf_warning,
                    'spf_record': spf_record,
                    'spf_key': settings.MAIL_CUSTOM_SENDER_SPF_STRING,
                    'recp': self.simple_form.cleaned_data.get('mail_from')
                },
                using=self.template_engine,
            )

        elif request.POST.get('mode') == 'smtp':
            if not self.smtp_form.is_valid():
                return super().get(request, *args, **kwargs)

            if request.POST.get('state') == 'save':
                for k, v in self.smtp_form.cleaned_data.items():
                    if v != SECRET_REDACTED:
                        self.object.settings.set(k, v)
                self.object.settings.smtp_use_custom = True
                self.log_action({**self.smtp_form.cleaned_data, 'smtp_use_custom': True})
                messages.success(request, _('Your changes have been saved.'))
                return redirect(self.get_success_url())
            else:
                self.smtp_form._unmask_secret_fields()

                backend = get_connection(
                    backend=settings.EMAIL_CUSTOM_SMTP_BACKEND,
                    host=self.smtp_form.cleaned_data['smtp_host'],
                    port=self.smtp_form.cleaned_data['smtp_port'],
                    username=self.smtp_form.cleaned_data.get('smtp_username', ''),
                    password=self.smtp_form.cleaned_data.get('smtp_password', ''),
                    use_tls=self.smtp_form.cleaned_data.get('smtp_use_tls', False),
                    use_ssl=self.smtp_form.cleaned_data.get('smtp_use_ssl', False),
                    fail_silently=False,
                    timeout=10,
                )
                try:
                    email.test_custom_smtp_backend(backend, self.smtp_form.cleaned_data.get('mail_from'))
                except Exception as e:
                    messages.error(self.request, _('An error occurred while contacting the SMTP server: %s') % str(e))
                    return self.get(request, *args, **kwargs)

                return self.response_class(
                    request=self.request,
                    template='pretixcontrol/email_setup_smtp.html',
                    context={
                        'basetpl': self.basetpl,
                        'object': self.object,
                        'known_host_problem': {
                            'smtp.gmail.com': _(
                                'We recommend not using Google Mail for transactional emails. If you try sending many '
                                'emails in a short amount of time, e.g. when sending information to all your ticket '
                                'buyers, there is a high chance Google will not deliver all of your emails since they '
                                'impose a maximum number of emails per time period.'
                            ),
                        }.get(self.smtp_form.cleaned_data['smtp_host']),
                    },
                    using=self.template_engine,
                )
