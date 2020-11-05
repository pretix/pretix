import base64
import json
import logging
import os
import time
from collections import defaultdict
from urllib.parse import quote, urlparse

import webauthn
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, ListView, TemplateView, UpdateView
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from pretix.base.auth import get_auth_backends
from pretix.base.forms.auth import ReauthForm
from pretix.base.forms.user import User2FADeviceAddForm, UserSettingsForm
from pretix.base.models import (
    Event, LogEntry, NotificationSetting, U2FDevice, User, WebAuthnDevice,
)
from pretix.base.models.auth import StaffSession
from pretix.base.notifications import get_all_notification_types
from pretix.control.forms.users import StaffSessionForm
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, StaffMemberRequiredMixin,
)
from pretix.control.views.auth import get_u2f_appid
from pretix.helpers.webauthn import generate_challenge, generate_ukey

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
                try:
                    wu = d.webauthnuser

                    if isinstance(d, U2FDevice):
                        # RP_ID needs to be appId for U2F devices, but we can't
                        # set it that way in U2FDevice.webauthnuser, since that
                        # breaks the frontend part.
                        wu.rp_id = settings.SITE_URL

                    webauthn_assertion_response = webauthn.WebAuthnAssertionResponse(
                        wu,
                        resp,
                        challenge,
                        settings.SITE_URL,
                        uv_required=False  # User Verification
                    )
                    sign_count = webauthn_assertion_response.verify()
                except Exception:
                    logger.exception('U2F login failed')
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
                return redirect(next_url)
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
                return redirect(next_url)
            return redirect(reverse('control:index'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        if 'webauthn_challenge' in self.request.session:
            del self.request.session['webauthn_challenge']
        challenge = generate_challenge(32)
        self.request.session['webauthn_challenge'] = challenge
        devices = [
            device.webauthnuser for device in WebAuthnDevice.objects.filter(confirmed=True, user=self.request.user)
        ] + [
            device.webauthnuser for device in U2FDevice.objects.filter(confirmed=True, user=self.request.user)
        ]
        if devices:
            webauthn_assertion_options = webauthn.WebAuthnAssertionOptions(
                devices,
                challenge
            )
            ad = webauthn_assertion_options.assertion_dict
            ad['extensions'] = {
                'appid': get_u2f_appid(self.request)
            }
            ctx['jsondata'] = json.dumps(ad)
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

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))

        data = {}
        for k in form.changed_data:
            if k not in ('old_pw', 'new_pw_repeat'):
                if 'new_pw' == k:
                    data['new_pw'] = True
                else:
                    data[k] = form.cleaned_data[k]

        msgs = []

        if 'new_pw' in form.changed_data:
            msgs.append(_('Your password has been changed.'))

        if 'email' in form.changed_data:
            msgs.append(_('Your email address has been changed to {email}.').format(email=form.cleaned_data['email']))

        if msgs:
            self.request.user.send_security_notice(msgs, email=form.cleaned_data['email'])
            if self._old_email != form.cleaned_data['email']:
                self.request.user.send_security_notice(msgs, email=self._old_email)

        sup = super().form_valid(form)
        self.request.user.log_action('pretix.user.settings.changed', user=self.request.user, data=data)

        update_session_auth_hash(self.request, self.request.user)
        return sup

    def get_success_url(self):
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

        challenge = generate_challenge(32)
        ukey = generate_ukey()

        self.request.session['webauthn_challenge'] = challenge
        self.request.session['webauthn_register_ukey'] = ukey

        make_credential_options = webauthn.WebAuthnMakeCredentialOptions(
            challenge,
            urlparse(settings.SITE_URL).netloc,
            urlparse(settings.SITE_URL).netloc,
            ukey,
            self.request.user.email,
            str(self.request.user),
            settings.SITE_URL
        )
        ctx['jsondata'] = json.dumps(make_credential_options.registration_dict)

        return ctx

    def post(self, request, *args, **kwargs):
        try:
            challenge = self.request.session['webauthn_challenge']
            ukey = self.request.session['webauthn_register_ukey']
            resp = json.loads(self.request.POST.get("token"))
            trust_anchor_dir = os.path.normpath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '../../static/webauthn_trusted_attestation_roots'  # currently does not exist
            ))
            # We currently do not check attestation certificates, since there's no real risk
            # and we do not have any policies specifying what devices can be used. (Also, we
            # didn't get it to work.)
            # Read more: https://fidoalliance.org/fido-technotes-the-truth-about-attestation/
            trusted_attestation_cert_required = False
            self_attestation_permitted = True
            none_attestation_permitted = True

            webauthn_registration_response = webauthn.WebAuthnRegistrationResponse(
                urlparse(settings.SITE_URL).netloc,
                settings.SITE_URL,
                resp,
                challenge,
                trust_anchor_dir,
                trusted_attestation_cert_required,
                self_attestation_permitted,
                none_attestation_permitted,
                uv_required=False
            )
            webauthn_credential = webauthn_registration_response.verify()

            # Check that the credentialId is not yet registered to any other user.
            # If registration is requested for a credential that is already registered
            # to a different user, the Relying Party SHOULD fail this registration
            # ceremony, or it MAY decide to accept the registration, e.g. while deleting
            # the older registration.
            credential_id_exists = WebAuthnDevice.objects.filter(
                credential_id=webauthn_credential.credential_id
            ).first()
            if credential_id_exists:
                messages.error(request, _('This security device is already registered.'))
                return redirect(reverse('control:user.settings.2fa.confirm.webauthn', kwargs={
                    'device': self.device.pk
                }))

            webauthn_credential.credential_id = str(webauthn_credential.credential_id, "utf-8")
            webauthn_credential.public_key = str(webauthn_credential.public_key, "utf-8")

            self.device.credential_id = webauthn_credential.credential_id
            self.device.ukey = ukey
            self.device.pub_key = webauthn_credential.public_key
            self.device.sign_count = webauthn_credential.sign_count
            self.device.rp_id = urlparse(settings.SITE_URL).netloc
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
                self.request.user.log_action('pretix.user.settings.notifications.disabled', user=self.request.user)
            else:
                self.request.user.log_action('pretix.user.settings.notifications.enabled', user=self.request.user)
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
            return redirect(request.GET.get("next"))
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
