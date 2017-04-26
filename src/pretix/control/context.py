import sys

from django.conf import settings
from django.core.urlresolvers import Resolver404, get_script_prefix, resolve

from pretix.base.settings import GlobalSettingsObject

from .signals import html_head, nav_event, nav_global, nav_topbar
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
    ctx['nav_event'] = _nav_event
    ctx['js_payment_weekdays_disabled'] = _js_payment_weekdays_disabled

    _nav_global = []
    if not hasattr(request, 'event'):
        for receiver, response in nav_global.send(request, request=request):
            _nav_global += response
    ctx['nav_global'] = _nav_global

    _nav_topbar = []
    for receiver, response in nav_topbar.send(request, request=request):
        _nav_topbar += response
    ctx['nav_topbar'] = _nav_topbar

    ctx['js_datetime_format'] = get_javascript_format('DATETIME_INPUT_FORMATS')
    ctx['js_date_format'] = get_javascript_format('DATE_INPUT_FORMATS')
    ctx['js_locale'] = get_moment_locale()

    if settings.DEBUG and 'runserver' not in sys.argv:
        ctx['debug_warning'] = True
    elif 'runserver' in sys.argv:
        ctx['development_warning'] = True

    ctx['warning_update_available'] = False
    ctx['warning_update_check_active'] = False
    if request.user.is_superuser:
        gs = GlobalSettingsObject()
        if gs.settings.update_check_result_warning:
            ctx['warning_update_available'] = True
        if not gs.settings.update_check_ack and 'runserver' not in sys.argv:
            ctx['warning_update_check_active'] = True

    return ctx
