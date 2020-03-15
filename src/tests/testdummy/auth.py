from collections import OrderedDict

from django import forms

from pretix.base.auth import BaseAuthBackend
from pretix.base.models import User


class TestFormAuthBackend(BaseAuthBackend):
    identifier = 'test_form'
    verbose_name = 'Form'

    @property
    def login_form_fields(self) -> dict:
        return OrderedDict([
            ('username', forms.CharField(max_length=100)),
            ('password', forms.CharField(max_length=100)),
        ])

    def form_authenticate(self, request, form_data):
        if form_data['username'] == 'foo' and form_data['password'] == 'bar':
            return User.objects.get_or_create(
                email='foo@example.com',
                auth_backend='test_form'
            )[0]


class TestRequestAuthBackend(BaseAuthBackend):
    identifier = 'test_request'
    verbose_name = 'Request'
    visible = False

    def request_authenticate(self, request):
        if 'X-Login-Email' in request.headers:
            return User.objects.get_or_create(
                email=request.headers['X-Login-Email'],
                auth_backend='test_request'
            )[0]

    def get_next_url(self, request):
        if 'state' in request.GET:
            return request.GET.get('state')
        return None
