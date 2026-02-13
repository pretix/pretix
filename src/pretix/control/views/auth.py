#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jason Estibeiro, Lukas Bockstaller, Maico Timmerman,
# Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import base64
import json
import logging
import time
from urllib.parse import quote, urljoin, urlparse

import webauthn
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate, login as auth_login, logout as auth_logout,
)
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView
from django_otp import match_token
from django_otp.plugins.otp_static.models import StaticDevice
from webauthn.helpers import generate_challenge

from pretix.base.auth import get_auth_backends
from pretix.base.forms.auth import (
    LoginForm, PasswordForgotForm, PasswordRecoverForm, RegistrationForm,
)
from pretix.base.metrics import pretix_failed_logins, pretix_successful_logins
from pretix.base.models import TeamInvite, U2FDevice, User, WebAuthnDevice
from pretix.helpers.http import get_client_ip, redirect_to_url
from pretix.helpers.security import handle_login_source

logger = logging.getLogger(__name__)


def process_login(request, user, keep_logged_in):
    """
    This method allows you to return a response to a successful log-in. This will set all session values correctly
    and redirect to either the URL specified in the ``next`` parameter, or the 2FA login screen, or the dashboard.

    :return: This method returns a ``HttpResponse``.
    """
    request.session['pretix_auth_long_session'] = settings.PRETIX_LONG_SESSIONS and keep_logged_in
    next_url = get_auth_backends()[user.auth_backend].get_next_url(request)
    if user.require_2fa:
        logger.info(f"Backend login redirected to 2FA for user {user.pk}.")
        request.session['pretix_auth_2fa_user'] = user.pk
        request.session['pretix_auth_2fa_time'] = str(int(time.time()))
        twofa_url = reverse('control:auth.login.2fa')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
            twofa_url += '?next=' + quote(next_url)
        return redirect_to_url(twofa_url)
    else:
        logger.info(f"Backend login successful for user {user.pk}.")
        pretix_successful_logins.inc(1)
        handle_login_source(user, request)
        auth_login(request, user)
        t = int(time.time())
        request.session['pretix_auth_login_time'] = t
        request.session['pretix_auth_last_used'] = t
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
            return redirect_to_url(next_url)
        return redirect('control:index')


def login(request):
    """
    Render and process a most basic login form. Takes an URL as GET
    parameter "next" for redirection after successful login
    """
    ctx = {}
    backenddict = get_auth_backends()
    backends = sorted(backenddict.values(), key=lambda b: (b.identifier != "native", b.verbose_name))
    for b in backends:
        u = b.request_authenticate(request)
        if u and u.auth_backend == b.identifier:
            return process_login(request, u, False)
        b.url = b.authentication_url(request)

    # Login should only happen on configured main domain
    good_origin = urlparse(settings.SITE_URL).scheme + '://' + urlparse(settings.SITE_URL).hostname

    backend = backenddict.get(request.GET.get('backend', 'native'), backends[0])
    if not backend.visible:
        backend = [b for b in backends if b.visible][0]
    if request.user.is_authenticated:
        next_url = backend.get_next_url(request) or 'control:index'
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
            return redirect_to_url(next_url)
        return redirect(reverse('control:index'))
    if request.method == 'POST':
        form = LoginForm(backend=backend, data=request.POST, request=request)
        is_valid = form.is_valid() and form.user_cache and form.user_cache.auth_backend == backend.identifier

        if form.cleaned_data.get("origin"):
            form_origin = form.cleaned_data.get("origin")
            if good_origin != form_origin:
                logger.warning(
                    f"Received login form submission with unexpected origin value. "
                    f"Origin sent from JavaScript: {form_origin} / "
                    f"Expected origin from configuration: {good_origin} / "
                    f"HTTP Host header: {request.headers.get('Host')} / "
                    f"HTTP origin header: {request.headers.get('Origin')} / "
                    f"HTTP referer header: {request.headers.get('Referer')} / "
                    f"IP address: {get_client_ip(request)} / "
                    f"Login result: {is_valid}"
                )

        if is_valid:
            return process_login(request, form.user_cache, form.cleaned_data.get('keep_logged_in', False))
    else:
        form = LoginForm(backend=backend, request=request)
    ctx['form'] = form
    ctx['can_register'] = settings.PRETIX_REGISTRATION
    ctx['can_reset'] = settings.PRETIX_PASSWORD_RESET
    ctx['backends'] = backends
    ctx['backend'] = backend
    ctx['good_origin'] = good_origin[::-1]  # minimal obfuscation against standard link rewriting
    ctx['bad_origin_report_url'] = urljoin(
        # as an additional safeguard always use SITE_URL, not anything derived from request
        settings.SITE_URL,
        reverse('control:auth.bad_origin_report')
    )[::-1]
    return render(request, 'pretixcontrol/auth/login.html', ctx)


@csrf_exempt
@require_http_methods(["POST"])
def bad_origin_report(request):
    good_origin = urlparse(settings.SITE_URL).scheme + '://' + urlparse(settings.SITE_URL).hostname
    form_origin = request.POST.get("origin")
    if good_origin != form_origin:
        logger.warning(
            f"Received report of unexpected origin value. "
            f"Origin sent from JavaScript: {form_origin} / "
            f"Expected origin from configuration: {good_origin} / "
            f"HTTP Host header: {request.headers.get('Host')} / "
            f"HTTP origin header: {request.headers.get('Origin')} / "
            f"HTTP referer header: {request.headers.get('Referer')} / "
            f"IP address: {get_client_ip(request)}"
        )
    resp = HttpResponse()
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


def logout(request):
    """
    Log the user out of the current session, then redirect to login page.
    """
    auth_logout(request)
    request.session['pretix_auth_login_time'] = 0
    next = reverse('control:auth.login')
    if 'next' in request.GET and url_has_allowed_host_and_scheme(request.GET.get('next'), allowed_hosts=None):
        next += '?next=' + quote(request.GET.get('next'))
    if 'back' in request.GET and url_has_allowed_host_and_scheme(request.GET.get('back'), allowed_hosts=None):
        return redirect_to_url(request.GET.get('back'))
    return redirect_to_url(next)


def register(request):
    """
    Render and process a basic registration form.
    """
    if not settings.PRETIX_REGISTRATION or 'native' not in get_auth_backends():
        raise PermissionDenied('Registration is disabled')
    ctx = {}
    if request.user.is_authenticated:
        next_url = request.GET.get("next") or reverse("control:index")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
            return redirect_to_url(next_url)
        return redirect("control:index")
    if request.method == 'POST':
        form = RegistrationForm(data=request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                form.cleaned_data['email'], form.cleaned_data['password'],
                locale=request.LANGUAGE_CODE,
                timezone=request.timezone if hasattr(request, 'timezone') else settings.TIME_ZONE
            )
            user = authenticate(request=request, email=user.email, password=form.cleaned_data['password'])
            user.log_action('pretix.control.auth.user.created', user=user)
            auth_login(request, user)
            request.session['pretix_auth_login_time'] = int(time.time())
            request.session['pretix_auth_long_session'] = (
                settings.PRETIX_LONG_SESSIONS and form.cleaned_data.get('keep_logged_in', False)
            )
            return redirect('control:index')
    else:
        form = RegistrationForm()
    ctx['form'] = form
    return render(request, 'pretixcontrol/auth/register.html', ctx)


def invite(request, token):
    """
    Registration form in case of an invite
    """
    ctx = {}

    if 'native' not in get_auth_backends():
        raise PermissionDenied('Invites are disabled')

    try:
        inv = TeamInvite.objects.get(token=token)
    except TeamInvite.DoesNotExist:
        messages.error(request, _('You used an invalid link. Please copy the link from your email to the address bar '
                                  'and make sure it is correct and that the link has not been used before.'))
        return redirect('control:auth.login')

    if request.user.is_authenticated:
        if inv.team.members.filter(pk=request.user.pk).exists():
            messages.error(request, _('You cannot accept the invitation for "{}" as you already are part of '
                                      'this team.').format(inv.team.name))
            return redirect('control:index')
        else:
            with transaction.atomic():
                if request.user.email.lower() == inv.email.lower():
                    request.user.is_verified = True
                    request.user.save(update_fields=['is_verified'])
                inv.team.members.add(request.user)
                inv.team.log_action(
                    'pretix.team.member.joined', data={
                        'email': request.user.email,
                        'invite_email': inv.email,
                        'user': request.user.pk
                    }
                )
                inv.delete()
            messages.success(request, _('You are now part of the team "{}".').format(inv.team.name))
            return redirect('control:index')

    if request.method == 'POST':
        form = RegistrationForm(data=request.POST)
        with transaction.atomic():
            valid = form.is_valid()
            if valid:
                user = User.objects.create_user(
                    form.cleaned_data['email'], form.cleaned_data['password'],
                    locale=request.LANGUAGE_CODE,
                    timezone=request.timezone if hasattr(request, 'timezone') else settings.TIME_ZONE,
                    is_verified=form.cleaned_data['email'].lower() == inv.email.lower()
                )
                user = authenticate(request=request, email=user.email, password=form.cleaned_data['password'])
                user.log_action('pretix.control.auth.user.created', user=user)
                auth_login(request, user)
                request.session['pretix_auth_login_time'] = int(time.time())
                request.session['pretix_auth_long_session'] = (
                    settings.PRETIX_LONG_SESSIONS and form.cleaned_data.get('keep_logged_in', False)
                )

                inv.team.members.add(request.user)
                inv.team.log_action(
                    'pretix.team.member.joined', data={
                        'email': user.email,
                        'invite_email': inv.email,
                        'user': user.pk
                    }
                )
                inv.delete()
                messages.success(request, _('Welcome to pretix! You are now part of the team "{}".').format(inv.team.name))
                return redirect('control:index')
    else:
        form = RegistrationForm(initial={'email': inv.email})
    ctx['form'] = form
    return render(request, 'pretixcontrol/auth/invite.html', ctx)


class RepeatedResetDenied(Exception):
    pass


class Forgot(TemplateView):
    template_name = 'pretixcontrol/auth/forgot.html'

    def dispatch(self, request, *args, **kwargs):
        if not settings.PRETIX_PASSWORD_RESET or 'native' not in get_auth_backends():
            raise PermissionDenied('Password reset is disabled')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            next_url = request.GET.get("next") or reverse("control:index")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
                return redirect_to_url(next_url)
            return redirect("control:index")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            email = self.form.cleaned_data['email']

            has_redis = settings.HAS_REDIS

            try:
                user = User.objects.get(is_active=True, auth_backend='native', email__iexact=email)

                if has_redis:
                    from django_redis import get_redis_connection
                    rc = get_redis_connection("redis")
                    if rc.exists('pretix_pwreset_%s' % (user.id)):
                        user.log_action('pretix.control.auth.user.forgot_password.denied.repeated')
                        raise RepeatedResetDenied()
                    else:
                        rc.setex('pretix_pwreset_%s' % (user.id), 3600 * 24, '1')

            except User.DoesNotExist:
                logger.warning('Backend password reset for unregistered e-mail \"' + email + '\" requested.')

            except RepeatedResetDenied:
                pass

            else:
                user.send_password_reset()
                user.log_action('pretix.control.auth.user.forgot_password.mail_sent')

            finally:
                if has_redis:
                    messages.info(request, _('If the address is registered to valid account, then we have sent you an email containing further instructions. '
                                             'Please note that we will send at most one email every 24 hours.'))
                else:
                    messages.info(request, _('If the address is registered to valid account, then we have sent you an email containing further instructions.'))

            return redirect('control:auth.forgot')
        else:
            return self.get(request, *args, **kwargs)

    @cached_property
    def form(self):
        return PasswordForgotForm(data=self.request.POST if self.request.method == 'POST' else None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        return context


class Recover(TemplateView):
    template_name = 'pretixcontrol/auth/recover.html'

    error_messages = {
        'invalid': _('You clicked on an invalid link. Please check that you copied the full '
                     'web address into your address bar. Please note that the link is only valid '
                     'for three days and that the link can only be used once.'),
        'unknownuser': _('We were unable to find the user you requested a new password for.')
    }

    def dispatch(self, request, *args, **kwargs):
        # settings.PRETIX_PASSWORD_RESET is not checked here to allow admin-sent recovery links
        if 'native' not in get_auth_backends():
            raise PermissionDenied('Registration is disabled')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            next_url = request.GET.get("next") or reverse("control:index")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
                return redirect_to_url(next_url)
            return redirect("control:index")
        try:
            user = User.objects.get(id=self.request.GET.get('id'), is_active=True, auth_backend='native')
        except User.DoesNotExist:
            return self.invalid('unknownuser')
        if not default_token_generator.check_token(user, self.request.GET.get('token')):
            return self.invalid('invalid')
        return super().get(request, *args, **kwargs)

    def invalid(self, msg):
        messages.error(self.request, self.error_messages[msg])
        return redirect('control:auth.forgot')

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            try:
                user = User.objects.get(id=self.request.GET.get('id'), auth_backend='native')
            except User.DoesNotExist:
                return self.invalid('unknownuser')
            if not default_token_generator.check_token(user, self.request.GET.get('token')):
                return self.invalid('invalid')
            user.set_password(self.form.cleaned_data['password'])
            user.needs_password_change = False
            user.save()
            messages.success(request, _('You can now login using your new password.'))
            user.log_action('pretix.control.auth.user.forgot_password.recovered')

            has_redis = settings.HAS_REDIS
            if has_redis:
                from django_redis import get_redis_connection
                rc = get_redis_connection("redis")
                rc.delete('pretix_pwreset_%s' % user.id)
            return redirect('control:auth.login')
        else:
            return self.get(request, *args, **kwargs)

    @cached_property
    def form(self):
        return PasswordRecoverForm(data=self.request.POST if self.request.method == 'POST' else None,
                                   user_id=self.request.GET.get('id'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        return context


def get_u2f_appid(request):
    return settings.SITE_URL


def get_webauthn_rp_id(request):
    return urlparse(settings.SITE_URL).hostname


class Login2FAView(TemplateView):
    template_name = 'pretixcontrol/auth/login_2fa.html'

    @property
    def app_id(self):
        return get_u2f_appid(self.request)

    def dispatch(self, request, *args, **kwargs):
        fail = False
        if 'pretix_auth_2fa_user' not in request.session:
            fail = True
        else:
            try:
                self.user = User.objects.get(pk=request.session['pretix_auth_2fa_user'], is_active=True)
            except User.DoesNotExist:
                fail = True
        logintime = int(request.session.get('pretix_auth_2fa_time', '1'))
        if time.time() - logintime > 300:
            pretix_failed_logins.inc(1, reason="2fa-timeout")
            fail = True
        if fail:
            messages.error(request, _('Please try again.'))
            return redirect('control:auth.login')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        token = request.POST.get('token', '').strip().replace(' ', '')

        valid = False
        if 'webauthn_challenge' in self.request.session and token.startswith('{'):
            challenge = self.request.session['webauthn_challenge']

            resp = json.loads(self.request.POST.get("token"))
            try:
                devices = [WebAuthnDevice.objects.get(user=self.user, credential_id=resp.get("id"))]
            except WebAuthnDevice.DoesNotExist:
                devices = U2FDevice.objects.filter(user=self.user)

            for d in devices:
                credential_current_sign_count = d.sign_count if isinstance(d, WebAuthnDevice) else 0
                try:
                    webauthn_assertion_response = webauthn.verify_authentication_response(
                        credential=resp,
                        expected_challenge=base64.b64decode(challenge),
                        expected_rp_id=get_webauthn_rp_id(self.request),
                        expected_origin=settings.SITE_URL,
                        credential_public_key=d.webauthnpubkey,
                        credential_current_sign_count=credential_current_sign_count,
                    )
                    sign_count = webauthn_assertion_response.new_sign_count
                    if sign_count < credential_current_sign_count:
                        pretix_failed_logins.inc(1, reason="webauthn-replay")
                        raise Exception("Possible replay attack, sign count not higher")
                except Exception:
                    if isinstance(d, U2FDevice):
                        # https://www.w3.org/TR/webauthn/#sctn-appid-extension says
                        # "When verifying the assertion, expect that the rpIdHash MAY be the hash of the AppID instead of the RP ID."
                        try:
                            webauthn_assertion_response = webauthn.verify_authentication_response(
                                credential=resp,
                                expected_challenge=base64.b64decode(challenge),
                                expected_rp_id=get_u2f_appid(self.request),
                                expected_origin=settings.SITE_URL,
                                credential_public_key=d.webauthnpubkey,
                                credential_current_sign_count=credential_current_sign_count,
                            )
                            if webauthn_assertion_response.new_sign_count < 1:
                                raise Exception("Possible replay attack, sign count set")
                        except Exception:
                            pretix_failed_logins.inc(1, reason="u2f")
                            logger.exception('U2F login failed')
                        else:
                            valid = True
                            break
                    else:
                        pretix_failed_logins.inc(1, reason="webauthn")
                        logger.exception('Webauthn login failed')
                else:
                    if isinstance(d, WebAuthnDevice):
                        d.sign_count = sign_count
                        d.save()
                    valid = True
                    break
        else:
            valid = match_token(self.user, token)
            if isinstance(valid, StaticDevice):
                self.user.send_security_notice([
                    _("A recovery code for two-factor authentification was used to log in.")
                ])

        if valid:
            logger.info(f"Backend login successful for user {self.user.pk} with 2FA.")
            pretix_successful_logins.inc(1)
            handle_login_source(self.user, request)
            auth_login(request, self.user)
            request.session['pretix_auth_login_time'] = int(time.time())
            del request.session['pretix_auth_2fa_user']
            del request.session['pretix_auth_2fa_time']
            if "next" in request.GET and url_has_allowed_host_and_scheme(request.GET.get("next"), allowed_hosts=None):
                return redirect_to_url(request.GET.get("next"))
            return redirect('control:index')
        else:
            pretix_failed_logins.inc(1, reason="2fa")
            messages.error(request, _('Invalid code, please try again.'))
            return redirect('control:auth.login.2fa')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        if 'webauthn_challenge' in self.request.session:
            del self.request.session['webauthn_challenge']
        challenge = generate_challenge()
        self.request.session['webauthn_challenge'] = base64.b64encode(challenge).decode()
        devices = [
            device.webauthndevice for device in WebAuthnDevice.objects.filter(confirmed=True, user=self.user)
        ] + [
            device.webauthndevice for device in U2FDevice.objects.filter(confirmed=True, user=self.user)
        ]
        if devices:
            auth_options = webauthn.generate_authentication_options(
                rp_id=get_webauthn_rp_id(self.request),
                challenge=challenge,
                allow_credentials=devices,
            )

            # Backwards compatibility to U2F
            j = json.loads(webauthn.options_to_json(auth_options))
            j["extensions"] = {"appid": get_u2f_appid(self.request)}
            ctx['jsondata'] = json.dumps(j)
        return ctx

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
