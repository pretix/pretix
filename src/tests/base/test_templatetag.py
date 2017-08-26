from django.template import Context, Template
from django.test import RequestFactory

TEMPLATE_REPLACE_PAGE = Template("{% load urlreplace %}{% url_replace request 'page' 3 %}")


def test_urlreplace_add__first_parameter():
    factory = RequestFactory()
    request = factory.get('/customer/details')
    rendered = TEMPLATE_REPLACE_PAGE.render(Context({
        'request': request
    })).strip()
    assert rendered == 'page=3'


def test_urlreplace_add_parameter():
    factory = RequestFactory()
    request = factory.get('/customer/details?foo=bar')
    rendered = TEMPLATE_REPLACE_PAGE.render(Context({
        'request': request
    })).strip()
    assert rendered in ('foo=bar&amp;page=3', 'page=3&amp;foo=bar')


def test_urlreplace_replace_parameter():
    factory = RequestFactory()
    request = factory.get('/customer/details?page=15')
    rendered = TEMPLATE_REPLACE_PAGE.render(Context({
        'request': request
    })).strip()
    assert rendered == 'page=3'
