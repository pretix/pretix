import sys
from importlib import import_module

from django.conf import settings
from django.core.urlresolvers import Resolver404, get_script_prefix, resolve
from django.utils.translation import get_language

from pretix.base.settings import GlobalSettingsObject

from ..helpers.i18n import get_javascript_format, get_moment_locale
from .signals import html_head, nav_event, nav_global, nav_topbar

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


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
    if hasattr(request, 'event') and request.user.is_authenticated:
        for receiver, response in html_head.send(request.event, request=request):
            _html_head.append(response)
    ctx['html_head'] = "".join(_html_head)

    _js_payment_weekdays_disabled = '[]'
    _nav_event = []
    if getattr(request, 'event', None) and hasattr(request, 'organizer') and request.user.is_authenticated:
        for receiver, response in nav_event.send(request.event, request=request):
            _nav_event += response
        if request.event.settings.get('payment_term_weekdays'):
            _js_payment_weekdays_disabled = '[0,6]'

        ctx['has_domain'] = request.event.organizer.domains.exists()

        if not request.event.live and ctx['has_domain']:
            child_sess = request.session.get('child_session_{}'.format(request.event.pk))
            s = SessionStore()
            if not child_sess or not s.exists(child_sess):
                s['pretix_event_access_{}'.format(request.event.pk)] = request.session.session_key
                s.create()
                ctx['new_session'] = s.session_key
                request.session['child_session_{}'.format(request.event.pk)] = s.session_key
                request.session['event_access'] = True
            else:
                ctx['new_session'] = child_sess
                request.session['event_access'] = True

        if request.GET.get('subevent', ''):
            # Do not use .get() for lazy evaluation
            ctx['selected_subevents'] = request.event.subevents.filter(pk=request.GET.get('subevent'))

    ctx['nav_event'] = _nav_event
    ctx['js_payment_weekdays_disabled'] = _js_payment_weekdays_disabled

    _nav_global = []
    if not hasattr(request, 'event') and request.user.is_authenticated:
        for receiver, response in nav_global.send(request, request=request):
            _nav_global += response

    ctx['nav_global'] = sorted(_nav_global, key=lambda n: n['label'])

    _nav_topbar = []
    if request.user.is_authenticated:
        for receiver, response in nav_topbar.send(request, request=request):
            _nav_topbar += response
    ctx['nav_topbar'] = sorted(_nav_topbar, key=lambda n: n['label'])

    ctx['js_datetime_format'] = get_javascript_format('DATETIME_INPUT_FORMATS')
    ctx['js_date_format'] = get_javascript_format('DATE_INPUT_FORMATS')
    ctx['js_time_format'] = get_javascript_format('TIME_INPUT_FORMATS')
    ctx['js_locale'] = get_moment_locale()
    ctx['select2locale'] = get_language()[:2]

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
