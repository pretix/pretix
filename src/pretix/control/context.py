from django.conf import settings
from django.core.urlresolvers import Resolver404, get_script_prefix, resolve

from .signals import html_head, nav_event, nav_topbar
from .utils.i18n import get_javascript_format, get_moment_locale


def contextprocessor(request):
    """
    Adds data to all template contexts
    """
    try:
        url = resolve(request.path_info)
    except Resolver404:
        return {}

    if not request.path.startswith(get_script_prefix() + 'control'):
        return {}
    ctx = {
        'url_name': url.url_name,
        'settings': settings,
        'DEBUG': settings.DEBUG,
    }
    _html_head = []
    if hasattr(request, 'event'):
        for receiver, response in html_head.send(request.event, request=request):
            _html_head.append(response)
    ctx['html_head'] = "".join(_html_head)

    _js_payment_weekdays_disabled = '[]'
    _nav_event = []
    if hasattr(request, 'event'):
        for receiver, response in nav_event.send(request.event, request=request):
            _nav_event += response
        if request.event.settings.get('payment_term_weekdays'):
            _js_payment_weekdays_disabled = '[0,6]'
    ctx['js_payment_weekdays_disabled'] = _js_payment_weekdays_disabled
    ctx['nav_event'] = _nav_event

    _nav_topbar = []
    for receiver, response in nav_topbar.send(request, request=request):
        _nav_topbar += response
    ctx['nav_topbar'] = _nav_topbar

    ctx['js_datetime_format'] = get_javascript_format('DATETIME_INPUT_FORMATS')
    ctx['js_date_format'] = get_javascript_format('DATE_INPUT_FORMATS')
    ctx['js_locale'] = get_moment_locale()

    return ctx
