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
# This file contains Apache-licensed contributions copyrighted by: Ian Williams, Jakob Schnell, Maico Timmerman
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import base64
import json
import logging
import time
from collections import defaultdict
from urllib.parse import quote

import webauthn
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import BadRequest, PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, ListView, TemplateView, UpdateView
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_scopes import scopes_disabled
from webauthn.helpers import generate_challenge, generate_user_handle

from pretix.base.auth import get_auth_backends
from pretix.base.forms.auth import ConfirmationCodeForm, ReauthForm
from pretix.base.forms.user import (
    User2FADeviceAddForm, UserEmailChangeForm, UserPasswordChangeForm,
    UserSettingsForm,
)
from pretix.base.models import (
    Event, LogEntry, NotificationSetting, U2FDevice, User, WebAuthnDevice,
)
from pretix.base.models.auth import StaffSession
from pretix.base.notifications import get_all_notification_types
from pretix.control.forms.users import StaffSessionForm
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, StaffMemberRequiredMixin,
)
from pretix.control.views.auth import get_u2f_appid, get_webauthn_rp_id
from pretix.helpers.http import redirect_to_url
from pretix.helpers.u2f import websafe_encode

REAL_DEVICE_TYPES = (TOTPDevice, WebAuthnDevice, U2FDevice)
logger = logging.getLogger(__name__)


class RecentAuthenticationRequiredMixin:
    max_time = 3600

    def dispatch(self, request, *args, **kwargs):
        tdelta = time.time() - request.session.get('pretix_auth_login_time', 0)
        if tdelta > self.max_time:
            return redirect(reverse('control:user.reauth') + '?next=' + quote(request.get_full_path()))
        return super().dispatch(request, *args, **kwargs)


class ReauthView(TemplateView):
    template_name = 'pretixcontrol/user/reauth.html'

    def post(self, request, *args, **kwargs):
        r = request.POST.get("webauthn", "")
        valid = False

        if 'webauthn_challenge' in self.request.session and r.startswith('{'):
            challenge = self.request.session['webauthn_challenge']

            resp = json.loads(r)
            try:
                devices = [WebAuthnDevice.objects.get(user=self.request.user, credential_id=resp.get("id"))]
            except WebAuthnDevice.DoesNotExist:
                devices = U2FDevice.objects.filter(user=self.request.user)

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
                            logger.exception('U2F login failed')
                        else:
                            valid = True
                            break
                    else:
                        logger.exception('Webauthn login failed')
                else:
                    if isinstance(d, WebAuthnDevice):
                        d.sign_count = sign_count
                        d.save()
                    valid = True
                    break

        valid = valid or self.form.is_valid()

        if valid:
            t = int(time.time())
            request.session['pretix_auth_login_time'] = t
            request.session['pretix_auth_last_used'] = t
            next_url = get_auth_backends()[request.user.auth_backend].get_next_url(request)
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
                return redirect_to_url(next_url)
            return redirect(reverse('control:index'))
        else:
            messages.error(request, _('The password you entered was invalid, please try again.'))
            return self.get(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        backend = get_auth_backends()[request.user.auth_backend]
        u = backend.request_authenticate(request)
        if u and u == request.user:
            next_url = backend.get_next_url(request)
            t = int(time.time())
            request.session['pretix_auth_login_time'] = t
            request.session['pretix_auth_last_used'] = t
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
                return redirect_to_url(next_url)
            return redirect(reverse('control:index'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        if 'webauthn_challenge' in self.request.session:
            del self.request.session['webauthn_challenge']
        challenge = generate_challenge()
        self.request.session['webauthn_challenge'] = base64.b64encode(challenge).decode()
        devices = [
            device.webauthndevice for device in WebAuthnDevice.objects.filter(confirmed=True, user=self.request.user)
        ] + [
            device.webauthndevice for device in U2FDevice.objects.filter(confirmed=True, user=self.request.user)
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
        ctx['form'] = self.form
        return ctx

    @cached_property
    def form(self):
        return ReauthForm(
            user=self.request.user,
            backend=get_auth_backends()[self.request.user.auth_backend],
            request=self.request,
            data=self.request.POST if self.request.method == "POST" else None,
            initial={
                'email': self.request.user.email,
            }
        )


class UserSettings(UpdateView):
    model = User
    form_class = UserSettingsForm
    template_name = 'pretixcontrol/user/settings.html'

    def get_object(self, queryset=None):
        self._old_email = self.request.user.email
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved. See below for details.'))
        return super().form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))

        data = {}
        for k in form.changed_data:
            data[k] = form.cleaned_data[k]

        sup = super().form_valid(form)
        self.request.user.log_action('pretix.user.settings.changed', user=self.request.user, data=data)

        update_session_auth_hash(self.request, self.request.user)
        return sup

    def get_success_url(self):
        if "next" in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next"), allowed_hosts=None):
            return self.request.GET.get("next")
        return reverse('control:user.settings')


class UserHistoryView(ListView):
    template_name = 'pretixcontrol/user/history.html'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):
        qs = LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(User),
            object_id=self.request.user.pk
        ).select_related(
            'user', 'content_type', 'api_token', 'oauth_application', 'device'
        ).order_by('-datetime')
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        class FakeClass:
            def top_logentries(self):
                return ctx['logs']

        ctx['fakeobj'] = FakeClass()
        return ctx


class User2FAMainView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_main.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        try:
            ctx['static_tokens'] = StaticDevice.objects.get(user=self.request.user, name='emergency').token_set.all()
        except StaticDevice.MultipleObjectsReturned:
            ctx['static_tokens'] = StaticDevice.objects.filter(
                user=self.request.user, name='emergency'
            ).first().token_set.all()
        except StaticDevice.DoesNotExist:
            d = StaticDevice.objects.create(user=self.request.user, name='emergency')
            for i in range(10):
                d.token_set.create(token=get_random_string(length=12, allowed_chars='1234567890'))
            ctx['static_tokens'] = d.token_set.all()

        ctx['devices'] = []
        for dt in REAL_DEVICE_TYPES:
            objs = list(dt.objects.filter(user=self.request.user, confirmed=True))
            for obj in objs:
                if dt == TOTPDevice:
                    obj.devicetype = 'totp'
                elif dt == U2FDevice:
                    obj.devicetype = 'u2f'
                elif dt == WebAuthnDevice:
                    obj.devicetype = 'webauthn'
            ctx['devices'] += objs

        ctx['obligatory'] = None
        if settings.PRETIX_OBLIGATORY_2FA is True:
            ctx['obligatory'] = 'system'
        elif settings.PRETIX_OBLIGATORY_2FA == "staff" and self.request.user.is_staff:
            ctx['obligatory'] = 'staff'
        elif teams := self.request.user.teams.filter(require_2fa=True).select_related('organizer'):
            ctx['obligatory'] = 'team'
            ctx['obligatory_teams'] = teams

        return ctx


class User2FADeviceAddView(RecentAuthenticationRequiredMixin, FormView):
    form_class = User2FADeviceAddForm
    template_name = 'pretixcontrol/user/2fa_add.html'

    def form_valid(self, form):
        if form.cleaned_data['devicetype'] == 'totp':
            dev = TOTPDevice.objects.create(user=self.request.user, confirmed=False, name=form.cleaned_data['name'])
        elif form.cleaned_data['devicetype'] == 'webauthn':
            if not self.request.is_secure():
                messages.error(self.request,
                               _('Security devices are only available if pretix is served via HTTPS.'))
                return self.get(self.request, self.args, self.kwargs)
            dev = WebAuthnDevice.objects.create(user=self.request.user, confirmed=False, name=form.cleaned_data['name'])
        return redirect(reverse('control:user.settings.2fa.confirm.' + form.cleaned_data['devicetype'], kwargs={
            'device': dev.pk
        }))

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class User2FADeviceDeleteView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_delete.html'

    @cached_property
    def device(self):
        if self.kwargs['devicetype'] == 'totp':
            return get_object_or_404(TOTPDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=True)
        elif self.kwargs['devicetype'] == 'webauthn':
            return get_object_or_404(WebAuthnDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=True)
        elif self.kwargs['devicetype'] == 'u2f':
            return get_object_or_404(U2FDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['device'] = self.device
        return ctx

    def post(self, request, *args, **kwargs):
        self.request.user.log_action('pretix.user.settings.2fa.device.deleted', user=self.request.user, data={
            'id': self.device.pk,
            'name': self.device.name,
            'devicetype': self.kwargs['devicetype']
        })
        self.device.delete()
        msgs = [
            _('A two-factor authentication device has been removed from your account.')
        ]
        if not any(dt.objects.filter(user=self.request.user, confirmed=True) for dt in REAL_DEVICE_TYPES):
            self.request.user.require_2fa = False
            self.request.user.save()
            self.request.user.log_action('pretix.user.settings.2fa.disabled', user=self.request.user)
            msgs.append(_('Two-factor authentication has been disabled.'))

        self.request.user.send_security_notice(msgs)
        self.request.user.update_session_token()
        update_session_auth_hash(self.request, self.request.user)
        messages.success(request, _('The device has been removed.'))
        return redirect(reverse('control:user.settings.2fa'))


class User2FADeviceConfirmWebAuthnView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_confirm_webauthn.html'

    @cached_property
    def device(self):
        return get_object_or_404(WebAuthnDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=False)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['device'] = self.device

        if 'webauthn_register_ukey' in self.request.session:
            del self.request.session['webauthn_register_ukey']
        if 'webauthn_challenge' in self.request.session:
            del self.request.session['webauthn_challenge']

        challenge = generate_challenge()
        ukey = generate_user_handle()

        self.request.session['webauthn_challenge'] = base64.b64encode(challenge).decode()
        self.request.session['webauthn_register_ukey'] = base64.b64encode(ukey).decode()

        devices = [
            device.webauthndevice for device in WebAuthnDevice.objects.filter(confirmed=True, user=self.request.user)
        ] + [
            device.webauthndevice for device in U2FDevice.objects.filter(confirmed=True, user=self.request.user)
        ]
        make_credential_options = webauthn.generate_registration_options(
            rp_id=get_webauthn_rp_id(self.request),
            rp_name=get_webauthn_rp_id(self.request),
            user_id=ukey,
            user_name=self.request.user.email,
            challenge=challenge,
            exclude_credentials=devices,
        )
        ctx['jsondata'] = webauthn.options_to_json(make_credential_options)

        return ctx

    def post(self, request, *args, **kwargs):
        try:
            challenge = self.request.session['webauthn_challenge']
            ukey = self.request.session['webauthn_register_ukey']
            resp = json.loads(self.request.POST.get("token"))

            registration_verification = webauthn.verify_registration_response(
                credential=resp,
                expected_challenge=base64.b64decode(challenge),
                expected_rp_id=get_webauthn_rp_id(self.request),
                expected_origin=settings.SITE_URL,
            )

            # Check that the credentialId is not yet registered to any other user.
            # If registration is requested for a credential that is already registered
            # to a different user, the Relying Party SHOULD fail this registration
            # ceremony, or it MAY decide to accept the registration, e.g. while deleting
            # the older registration.
            credential_id_exists = WebAuthnDevice.objects.filter(
                credential_id=registration_verification.credential_id
            ).first()
            if credential_id_exists:
                messages.error(request, _('This security device is already registered.'))
                return redirect(reverse('control:user.settings.2fa.confirm.webauthn', kwargs={
                    'device': self.device.pk
                }))

            self.device.credential_id = websafe_encode(registration_verification.credential_id)
            self.device.ukey = websafe_encode(ukey)
            self.device.pub_key = websafe_encode(registration_verification.credential_public_key)
            self.device.sign_count = registration_verification.sign_count
            self.device.rp_id = get_webauthn_rp_id(request)
            self.device.icon_url = settings.SITE_URL
            self.device.confirmed = True
            self.device.save()
            self.request.user.log_action('pretix.user.settings.2fa.device.added', user=self.request.user, data={
                'id': self.device.pk,
                'devicetype': 'u2f',
                'name': self.device.name,
            })
            notices = [
                _('A new two-factor authentication device has been added to your account.')
            ]
            activate = request.POST.get('activate', '')
            if activate == 'on' and not self.request.user.require_2fa:
                self.request.user.require_2fa = True
                self.request.user.save()
                self.request.user.log_action('pretix.user.settings.2fa.enabled', user=self.request.user)
                notices.append(
                    _('Two-factor authentication has been enabled.')
                )
            self.request.user.send_security_notice(notices)
            self.request.user.update_session_token()
            update_session_auth_hash(self.request, self.request.user)

            note = ''
            if not self.request.user.require_2fa:
                note = ' ' + str(_('Please note that you still need to enable two-factor authentication for your '
                                   'account using the buttons below to make a second factor required for logging '
                                   'into your account.'))
            messages.success(request, str(_('The device has been verified and can now be used.')) + note)
            return redirect(reverse('control:user.settings.2fa'))
        except Exception:
            messages.error(request, _('The registration could not be completed. Please try again.'))
            logger.exception('WebAuthn registration failed')
            return redirect(reverse('control:user.settings.2fa.confirm.webauthn', kwargs={
                'device': self.device.pk
            }))


class User2FADeviceConfirmTOTPView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_confirm_totp.html'

    @cached_property
    def device(self):
        return get_object_or_404(TOTPDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=False)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        ctx['secret'] = base64.b32encode(self.device.bin_key).decode('utf-8')
        ctx['secretGrouped'] = "  ".join([ctx['secret'].lower()[(i * 4): (i + 1) * 4] for i in range(len(ctx['secret']) // 4)])
        ctx['qrdata'] = 'otpauth://totp/{label}%3A%20{user}?issuer={label}&secret={secret}&digits={digits}'.format(
            label=quote(settings.PRETIX_INSTANCE_NAME), user=quote(self.request.user.email),
            secret=ctx['secret'],
            digits=self.device.digits
        )
        ctx['device'] = self.device
        return ctx

    def post(self, request, *args, **kwargs):
        token = request.POST.get('token', '')
        activate = request.POST.get('activate', '')
        if self.device.verify_token(token):
            self.device.confirmed = True
            self.device.save()
            self.request.user.log_action('pretix.user.settings.2fa.device.added', user=self.request.user, data={
                'id': self.device.pk,
                'name': self.device.name,
                'devicetype': 'totp'
            })
            notices = [
                _('A new two-factor authentication device has been added to your account.')
            ]
            if activate == 'on' and not self.request.user.require_2fa:
                self.request.user.require_2fa = True
                self.request.user.save()
                self.request.user.log_action('pretix.user.settings.2fa.enabled', user=self.request.user)
                notices.append(
                    _('Two-factor authentication has been enabled.')
                )
            self.request.user.send_security_notice(notices)
            self.request.user.update_session_token()
            update_session_auth_hash(self.request, self.request.user)

            note = ''
            if not self.request.user.require_2fa:
                note = ' ' + str(_('Please note that you still need to enable two-factor authentication for your '
                                   'account using the buttons below to make a second factor required for logging '
                                   'into your account.'))
            messages.success(request, str(_('The device has been verified and can now be used.')) + note)
            return redirect(reverse('control:user.settings.2fa'))
        else:
            messages.error(request, _('The code you entered was not valid. If this problem persists, please check '
                                      'that the date and time of your phone are configured correctly.'))
            return redirect(reverse('control:user.settings.2fa.confirm.totp', kwargs={
                'device': self.device.pk
            }))


class User2FALeaveTeamsView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_leaveteams.html'

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        for team in self.request.user.teams.filter(require_2fa=True).select_related('organizer'):
            team.members.remove(self.request.user)
            team.log_action(
                'pretix.team.member.removed', user=self.request.user, data={
                    'email': self.request.user.email,
                    'user': self.request.user.pk
                }
            )
        messages.success(request, _('You have left all teams that require two-factor authentication.'))
        return redirect(reverse('control:user.settings.2fa'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['obligatory_teams'] = self.request.user.teams.filter(require_2fa=True).select_related('organizer')
        return ctx


class User2FAEnableView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_enable.html'

    def dispatch(self, request, *args, **kwargs):
        if not any(dt.objects.filter(user=self.request.user, confirmed=True) for dt in REAL_DEVICE_TYPES):
            messages.error(request, _('Please configure at least one device before enabling two-factor '
                                      'authentication.'))
            return redirect(reverse('control:user.settings.2fa'))
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.request.user.require_2fa = True
        self.request.user.save()
        self.request.user.log_action('pretix.user.settings.2fa.enabled', user=self.request.user)
        messages.success(request, _('Two-factor authentication is now enabled for your account.'))
        self.request.user.send_security_notice([
            _('Two-factor authentication has been enabled.')
        ])
        self.request.user.update_session_token()
        update_session_auth_hash(self.request, self.request.user)
        return redirect(reverse('control:user.settings.2fa'))


class User2FADisableView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_disable.html'

    def post(self, request, *args, **kwargs):
        self.request.user.require_2fa = False
        self.request.user.save()
        self.request.user.log_action('pretix.user.settings.2fa.disabled', user=self.request.user)
        messages.success(request, _('Two-factor authentication is now disabled for your account.'))
        self.request.user.send_security_notice([
            _('Two-factor authentication has been disabled.')
        ])
        self.request.user.update_session_token()
        update_session_auth_hash(self.request, self.request.user)
        return redirect(reverse('control:user.settings.2fa'))


class User2FARegenerateEmergencyView(RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/2fa_regenemergency.html'

    def post(self, request, *args, **kwargs):
        StaticDevice.objects.filter(user=self.request.user, name='emergency').delete()
        d = StaticDevice.objects.create(user=self.request.user, name='emergency')
        for i in range(10):
            d.token_set.create(token=get_random_string(length=12, allowed_chars='1234567890'))
        self.request.user.log_action('pretix.user.settings.2fa.regenemergency', user=self.request.user)
        self.request.user.send_security_notice([
            _('Your two-factor emergency codes have been regenerated.')
        ])
        self.request.user.update_session_token()
        update_session_auth_hash(self.request, self.request.user)
        messages.success(request, _('Your emergency codes have been newly generated. Remember to store them in a safe '
                                    'place in case you lose access to your devices.'))
        return redirect(reverse('control:user.settings.2fa'))


class UserNotificationsDisableView(TemplateView):
    template_name = 'pretixcontrol/user/notifications_disable.html'

    @scopes_disabled()
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        user = get_object_or_404(User, notifications_token=kwargs.get('token'), pk=kwargs.get('id'))
        user.notifications_send = False
        user.save()
        messages.success(request, _('Your notifications have been disabled.'))

        if request.user.is_authenticated:
            return redirect(
                reverse('control:user.settings.notifications')
            )
        else:
            return redirect(
                reverse('control:auth.login')
            )


class UserNotificationsEditView(TemplateView):
    template_name = 'pretixcontrol/user/notifications.html'

    @cached_property
    def event(self):
        if self.request.GET.get('event'):
            try:
                return self.request.user.get_events_with_any_permission().select_related(
                    'organizer'
                ).get(pk=self.request.GET.get('event'))
            except Event.DoesNotExist:
                return None
        return None

    @cached_property
    def types(self):
        return get_all_notification_types(self.event)

    @cached_property
    def currently_set(self):
        set_per_method = defaultdict(dict)
        for n in self.request.user.notification_settings.filter(event=self.event):
            set_per_method[n.method][n.action_type] = n.enabled
        return set_per_method

    @cached_property
    def global_set(self):
        set_per_method = defaultdict(dict)
        for n in self.request.user.notification_settings.filter(event__isnull=True):
            set_per_method[n.method][n.action_type] = n.enabled
        return set_per_method

    def post(self, request, *args, **kwargs):
        if "notifications_send" in request.POST:
            request.user.notifications_send = request.POST.get("notifications_send", "") == "on"
            request.user.save()

            messages.success(request, _('Your notification settings have been saved.'))
            if request.user.notifications_send:
                self.request.user.log_action('pretix.user.settings.notifications.enabled', user=self.request.user)
            else:
                self.request.user.log_action('pretix.user.settings.notifications.disabled', user=self.request.user)
            return redirect(
                reverse('control:user.settings.notifications') +
                ('?event={}'.format(self.event.pk) if self.event else '')
            )
        else:
            for method, __ in NotificationSetting.CHANNELS:
                old_enabled = self.currently_set[method]

                for at in self.types.keys():
                    val = request.POST.get('{}:{}'.format(method, at))

                    # True → False
                    if old_enabled.get(at) is True and val == 'off':
                        self.request.user.notification_settings.filter(
                            event=self.event, action_type=at, method=method
                        ).update(enabled=False)

                    # True/False → None
                    if old_enabled.get(at) is not None and val == 'global':
                        self.request.user.notification_settings.filter(
                            event=self.event, action_type=at, method=method
                        ).delete()

                    # None → True/False
                    if old_enabled.get(at) is None and val in ('on', 'off'):
                        self.request.user.notification_settings.create(
                            event=self.event, action_type=at, method=method, enabled=(val == 'on'),
                        )

                    # False → True
                    if old_enabled.get(at) is False and val == 'on':
                        self.request.user.notification_settings.filter(
                            event=self.event, action_type=at, method=method
                        ).update(enabled=True)

            messages.success(request, _('Your notification settings have been saved.'))
            self.request.user.log_action('pretix.user.settings.notifications.changed', user=self.request.user)
            return redirect(
                reverse('control:user.settings.notifications') +
                ('?event={}'.format(self.event.pk) if self.event else '')
            )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['events'] = self.request.user.get_events_with_any_permission().order_by('-date_from')
        ctx['types'] = [
            (
                tv,
                {k: a.get(t) for k, a in self.currently_set.items()},
                {k: a.get(t) for k, a in self.global_set.items()},
            )
            for t, tv in self.types.items()
        ]
        ctx['event'] = self.event
        if self.event:
            ctx['permset'] = self.request.user.get_event_permission_set(self.event.organizer, self.event)
        return ctx


class StartStaffSession(StaffMemberRequiredMixin, RecentAuthenticationRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/user/staff_session_start.html'

    def post(self, request, *args, **kwargs):
        if not request.user.has_active_staff_session(request.session.session_key):
            StaffSession.objects.create(
                user=request.user,
                session_key=request.session.session_key
            )

        if "next" in request.GET and url_has_allowed_host_and_scheme(request.GET.get("next"), allowed_hosts=None):
            return redirect_to_url(request.GET.get("next"))
        else:
            return redirect(reverse("control:index"))


class StopStaffSession(StaffMemberRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        session = StaffSession.objects.filter(
            date_end__isnull=True, session_key=request.session.session_key, user=request.user,
        ).first()
        if not session:
            return redirect(reverse("control:index"))

        session.date_end = now()
        session.save()
        return redirect(reverse("control:user.sudo.edit", kwargs={'id': session.pk}))


class StaffSessionList(AdministratorPermissionRequiredMixin, ListView):
    context_object_name = 'sessions'
    template_name = 'pretixcontrol/user/staff_session_list.html'
    paginate_by = 25
    model = StaffSession

    def get_queryset(self):
        return StaffSession.objects.select_related('user').order_by('-date_start')


class EditStaffSession(StaffMemberRequiredMixin, UpdateView):
    context_object_name = 'session'
    template_name = 'pretixcontrol/user/staff_session_edit.html'
    form_class = StaffSessionForm

    def get_success_url(self):
        return reverse("control:user.sudo.edit", kwargs={'id': self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['logs'] = self.object.logs.select_related('impersonating')
        return ctx

    def form_valid(self, form):
        messages.success(self.request, _('Your comment has been saved.'))
        return super().form_valid(form)

    def get_object(self, queryset=None):
        if self.request.user.has_active_staff_session(self.request.session.session_key):
            return get_object_or_404(StaffSession, pk=self.kwargs['id'])
        else:
            return get_object_or_404(StaffSession, pk=self.kwargs['id'], user=self.request.user)


class UserPasswordChangeView(FormView):
    max_time = 300

    form_class = UserPasswordChangeForm
    template_name = 'pretixcontrol/user/change_password.html'

    def get_form_kwargs(self):
        if self.request.user.auth_backend != 'native':
            raise PermissionDenied

        return {
            **super().get_form_kwargs(),
            "user": self.request.user,
        }

    def form_valid(self, form):
        with transaction.atomic():
            self.request.user.set_password(form.cleaned_data['new_pw'])
            self.request.user.needs_password_change = False
            self.request.user.save()
            msgs = []
            msgs.append(_('Your password has been changed.'))
            self.request.user.send_security_notice(msgs)

            self.request.user.log_action('pretix.user.settings.changed', user=self.request.user, data={'new_pw': True})

            update_session_auth_hash(self.request, self.request.user)

        messages.success(self.request, _('Your changes have been saved.'))
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_success_url(self):
        if "next" in self.request.GET and url_has_allowed_host_and_scheme(self.request.GET.get("next"), allowed_hosts=None):
            return self.request.GET.get("next")
        return reverse('control:user.settings')


class UserEmailChangeView(RecentAuthenticationRequiredMixin, FormView):
    max_time = 300

    form_class = UserEmailChangeForm
    template_name = 'pretixcontrol/user/change_email.html'

    def get_form_kwargs(self):
        if self.request.user.auth_backend != 'native':
            raise PermissionDenied

        return {
            **super().get_form_kwargs(),
            "user": self.request.user,
        }

    def get_initial(self):
        return {
            "old_email": self.request.user.email
        }

    def form_valid(self, form):
        self.request.user.send_confirmation_code(
            session=self.request.session,
            reason='email_change',
            email=form.cleaned_data['new_email'],
            state=form.cleaned_data['new_email'],
        )
        self.request.session['email_confirmation_destination'] = form.cleaned_data['new_email']
        return redirect(reverse('control:user.settings.email.confirm', kwargs={}) + '?reason=email_change')

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class UserEmailVerifyView(View):
    def post(self, request, *args, **kwargs):
        if self.request.user.is_verified:
            messages.success(self.request, _('Your email address was already verified.'))
            return redirect(reverse('control:user.settings', kwargs={}))

        self.request.user.send_confirmation_code(
            session=self.request.session,
            reason='email_verify',
            email=self.request.user.email,
            state=self.request.user.email,
        )
        self.request.session['email_confirmation_destination'] = self.request.user.email
        return redirect(reverse('control:user.settings.email.confirm', kwargs={}) + '?reason=email_verify')


class UserEmailConfirmView(FormView):
    form_class = ConfirmationCodeForm
    template_name = 'pretixcontrol/user/confirmation_code_dialog.html'

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "cancel_url": reverse('control:user.settings', kwargs={}),
            "message": format_html(
                _("Please enter the confirmation code we sent to your email address <strong>{email}</strong>."),
                email=self.request.session.get('email_confirmation_destination', ''),
            ),
        }

    @transaction.atomic()
    def form_valid(self, form):
        reason = self.request.GET['reason']
        if reason not in ('email_change', 'email_verify'):
            raise PermissionDenied
        try:
            new_email = self.request.user.check_confirmation_code(
                session=self.request.session,
                reason=reason,
                code=form.cleaned_data['code'],
            )
        except PermissionDenied:
            return self.form_invalid(form)
        except BadRequest:
            messages.error(self.request, _(
                'We were unable to verify your confirmation code. Please try again.'
            ))
            return redirect(reverse('control:user.settings', kwargs={}))

        log_data = {
            'email': new_email,
            'email_verified': True,
        }
        if reason == 'email_change':
            msgs = []
            msgs.append(_('Your email address has been changed to {email}.').format(email=new_email))
            log_data['old_email'] = old_email = self.request.user.email
            self.request.user.send_security_notice(msgs, email=old_email)
            self.request.user.send_security_notice(msgs, email=new_email)
            log_action = 'pretix.user.email.changed'
        else:
            log_action = 'pretix.user.email.confirmed'

        self.request.user.email = new_email
        self.request.user.is_verified = True
        self.request.user.save()
        self.request.user.log_action(log_action, user=self.request.user, data=log_data)
        update_session_auth_hash(self.request, self.request.user)

        if reason == 'email_change':
            messages.success(self.request, _('Your email address has been changed successfully.'))
        else:
            messages.success(self.request, _('Your email address has been confirmed successfully.'))
        return redirect(reverse('control:user.settings', kwargs={}))

    def form_invalid(self, form):
        messages.error(self.request, _('The entered confirmation code is not correct. Please try again.'))
        return super().form_invalid(form)
