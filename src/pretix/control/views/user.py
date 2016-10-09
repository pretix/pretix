import base64
import copy
import logging
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, redirect
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView, TemplateView, UpdateView
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from u2flib_server import u2f
from u2flib_server.jsapi import DeviceRegistration

from pretix.base.forms.user import User2FADeviceAddForm, UserSettingsForm
from pretix.base.models import U2FDevice, User
from pretix.control.views.auth import get_u2f_appid

REAL_DEVICE_TYPES = (TOTPDevice, U2FDevice)
logger = logging.getLogger(__name__)


class UserSettings(UpdateView):
    model = User
    form_class = UserSettingsForm
    template_name = 'pretixcontrol/user/settings.html'

    def get_object(self, queryset=None):
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
        sup = super().form_valid(form)

        data = {}
        for k in form.changed_data:
            if k not in ('old_pw', 'new_pw_repeat'):
                if 'new_pw' == k:
                    data['new_pw'] = True
                else:
                    data[k] = form.cleaned_data[k]
        self.request.user.log_action('pretix.user.settings.changed', user=self.request.user, data=data)

        update_session_auth_hash(self.request, self.request.user)
        return sup

    def get_success_url(self):
        return reverse('control:user.settings')


class User2FAMainView(TemplateView):
    template_name = 'pretixcontrol/user/2fa_main.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        try:
            ctx['static_tokens'] = StaticDevice.objects.get(user=self.request.user, name='emergency').token_set.all()
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
            ctx['devices'] += objs

        return ctx


class User2FADeviceAddView(FormView):
    form_class = User2FADeviceAddForm
    template_name = 'pretixcontrol/user/2fa_add.html'

    def form_valid(self, form):
        if form.cleaned_data['devicetype'] == 'totp':
            dev = TOTPDevice.objects.create(user=self.request.user, confirmed=False, name=form.cleaned_data['name'])
        elif form.cleaned_data['devicetype'] == 'u2f':
            if not self.request.is_secure():
                messages.error(self.request, _('U2F devices are only available if pretix is served via HTTPS.'))
                return self.get(self.request, self.args, self.kwargs)
            dev = U2FDevice.objects.create(user=self.request.user, confirmed=False, name=form.cleaned_data['name'])
        return redirect(reverse('control:user.settings.2fa.confirm.' + form.cleaned_data['devicetype'], kwargs={
            'device': dev.pk
        }))


class User2FADeviceDeleteView(TemplateView):
    template_name = 'pretixcontrol/user/2fa_delete.html'

    @cached_property
    def device(self):
        if self.kwargs['devicetype'] == 'totp':
            return get_object_or_404(TOTPDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=True)
        elif self.kwargs['devicetype'] == 'u2f':
            return get_object_or_404(U2FDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['device'] = self.device
        return ctx

    def post(self, request, *args, **kwargs):
        self.request.user.log_action('pretix.user.settings.2fa.device.deleted', user=self.request.user, data={
            'id': self.device.pk
        })
        self.device.delete()
        if not any(dt.objects.filter(user=self.request.user, confirmed=True) for dt in REAL_DEVICE_TYPES):
            self.request.user.require_2fa = False
            self.request.user.save()
            self.request.user.log_action('pretix.user.settings.2fa.disabled', user=self.request.user)

        messages.success(request, _('The device has been removed.'))
        return redirect(reverse('control:user.settings.2fa'))


class User2FADeviceConfirmU2FView(TemplateView):
    template_name = 'pretixcontrol/user/2fa_confirm_u2f.html'

    @property
    def app_id(self):
        return get_u2f_appid(self.request)

    @cached_property
    def device(self):
        return get_object_or_404(U2FDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=False)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['device'] = self.device

        devices = [DeviceRegistration.wrap(device.json_data)
                   for device in U2FDevice.objects.filter(confirmed=True, user=self.request.user)]
        enroll = u2f.start_register(self.app_id, devices)
        self.request.session['_u2f_enroll'] = enroll.json
        ctx['jsondata'] = enroll.json

        return ctx

    def post(self, request, *args, **kwargs):
        try:
            binding, cert = u2f.complete_register(self.request.session.pop('_u2f_enroll'),
                                                  request.POST.get('token'),
                                                  [self.app_id])
            self.device.json_data = binding.json
            self.device.confirmed = True
            self.device.save()
            self.request.user.log_action('pretix.user.settings.2fa.device.added', user=self.request.user, data={
                'id': self.device.pk,
                'devicetype': 'u2f'
            })

            messages.success(request, _('The device has been verified and can now be used.'))
            return redirect(reverse('control:user.settings.2fa'))
        except Exception:
            messages.error(request, _('The registration could not be completed. Please try again.'))
            logger.exception('U2F registration failed')
            return redirect(reverse('control:user.settings.2fa.confirm.u2f', kwargs={
                'device': self.device.pk
            }))


class User2FADeviceConfirmTOTPView(TemplateView):
    template_name = 'pretixcontrol/user/2fa_confirm_totp.html'

    @cached_property
    def device(self):
        return get_object_or_404(TOTPDevice, user=self.request.user, pk=self.kwargs['device'], confirmed=False)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        ctx['secret'] = base64.b32encode(self.device.bin_key).decode('utf-8')
        ctx['qrdata'] = 'otpauth://totp/{label}%3A%20{user}?issuer={label}&secret={secret}&digits={digits}'.format(
            label=quote(settings.PRETIX_INSTANCE_NAME), user=quote(self.request.user.email),
            secret=ctx['secret'],
            digits=self.device.digits
        )
        ctx['device'] = self.device
        return ctx

    def post(self, request, *args, **kwargs):
        token = request.POST.get('token', '')
        if self.device.verify_token(token):
            self.device.confirmed = True
            self.device.save()
            self.request.user.log_action('pretix.user.settings.2fa.device.added', user=self.request.user, data={
                'id': self.device.pk,
                'devicetype': 'totp'
            })

            messages.success(request, _('The device has been verified and can now be used.'))
            return redirect(reverse('control:user.settings.2fa'))
        else:
            messages.error(request, _('The code you entered was not valid. If this problem persists, please check '
                                      'that the date and time of your phone are configured correctly.'))
            return redirect(reverse('control:user.settings.2fa.confirm.totp', kwargs={
                'device': self.device.pk
            }))


class User2FAEnableView(TemplateView):
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
        return redirect(reverse('control:user.settings.2fa'))


class User2FADisableView(TemplateView):
    template_name = 'pretixcontrol/user/2fa_disable.html'

    def post(self, request, *args, **kwargs):
        self.request.user.require_2fa = False
        self.request.user.save()
        self.request.user.log_action('pretix.user.settings.2fa.disabled', user=self.request.user)
        messages.success(request, _('Two-factor authentication is now disabled for your account.'))
        return redirect(reverse('control:user.settings.2fa'))


class User2FARegenerateEmergencyView(TemplateView):
    template_name = 'pretixcontrol/user/2fa_regenemergency.html'

    def post(self, request, *args, **kwargs):
        d = StaticDevice.objects.get(user=self.request.user, name='emergency')
        d.token_set.all().delete()
        for i in range(10):
            d.token_set.create(token=get_random_string(length=12, allowed_chars='1234567890'))
        self.request.user.log_action('pretix.user.settings.2fa.regenemergency', user=self.request.user)
        messages.success(request, _('Your emergency codes have been newly generated. Remember to store them in a safe '
                                    'place in case you lose access to your devices.'))
        return redirect(reverse('control:user.settings.2fa'))
