import base64
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView, TemplateView, UpdateView
from django_otp.plugins.otp_totp.models import TOTPDevice

from pretix.base.forms.user import User2FADeviceAddForm, UserSettingsForm
from pretix.base.models import User


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
        update_session_auth_hash(self.request, self.request.user)
        return sup

    def get_success_url(self):
        return reverse('control:user.settings')


class User2FAMainView(TemplateView):
    template_name = 'pretixcontrol/user/2fa_main.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        ctx['devices'] = []
        for dt in (TOTPDevice,):
            objs = list(dt.objects.filter(user=self.request.user, confirmed=True))
            for obj in objs:
                if dt == TOTPDevice:
                    obj.devicetype = 'totp'
            ctx['devices'] += objs

        return ctx


class User2FADeviceAddView(FormView):
    form_class = User2FADeviceAddForm
    template_name = 'pretixcontrol/user/2fa_add.html'

    def form_valid(self, form):
        if form.cleaned_data['devicetype'] == 'totp':
            dev = TOTPDevice.objects.create(user=self.request.user, confirmed=False, name=form.cleaned_data['name'])
        else:
            messages.error(self.request, _('Unknown device type'))
            return self.get(self.request, self.args, self.kwargs)
        return redirect(reverse('control:user.settings.2fa.confirm.' + form.cleaned_data['devicetype'], kwargs={
            'device': dev.pk
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
            messages.success(request, _('The device has been verified and can now be used.'))
            return redirect(reverse('control:user.settings.2fa'))
        else:
            messages.error(request, _('The code you entered was not valid. If this problem persists, please check '
                                      'that the date and time of your phone are configured correctly.'))
            return redirect(reverse('control:user.settings.2fa.confirm.totp', kwargs={
                'device': self.device.pk
            }))
