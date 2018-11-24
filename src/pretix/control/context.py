import sys
from importlib import import_module

from django.conf import settings
from django.db.models import Q
from django.urls import Resolver404, get_script_prefix, resolve
from django.utils.translation import get_language

from pretix.base.models.auth import StaffSession
from pretix.base.settings import GlobalSettingsObject
from pretix.control.navigation import (
    get_event_navigation, get_global_navigation, get_organizer_navigation,
)

from ..helpers.i18n import (
    get_javascript_format, get_javascript_output_format, get_moment_locale,
)
from .signals import html_head, nav_topbar

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
    if getattr(request, 'event', None) and hasattr(request, 'organizer') and request.user.is_authenticated:
        ctx['nav_items'] = get_event_navigation(request)

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
    elif getattr(request, 'organizer', None) and request.user.is_authenticated:
        ctx['nav_items'] = get_organizer_navigation(request)
    elif request.user.is_authenticated:
        ctx['nav_items'] = get_global_navigation(request)

    ctx['js_payment_weekdays_disabled'] = _js_payment_weekdays_disabled

    _nav_topbar = []
    if request.user.is_authenticated:
        for receiver, response in nav_topbar.send(request, request=request):
            _nav_topbar += response
    ctx['nav_topbar'] = sorted(_nav_topbar, key=lambda n: n['label'])

    ctx['js_datetime_format'] = get_javascript_format('DATETIME_INPUT_FORMATS')
    ctx['js_date_format'] = get_javascript_format('DATE_INPUT_FORMATS')
    ctx['js_long_date_format'] = get_javascript_output_format('DATE_FORMAT')
    ctx['js_time_format'] = get_javascript_format('TIME_INPUT_FORMATS')
    ctx['js_locale'] = get_moment_locale()
    ctx['select2locale'] = get_language()[:2]

    if settings.DEBUG and 'runserver' not in sys.argv:
        ctx['debug_warning'] = True
    elif 'runserver' in sys.argv:
        ctx['development_warning'] = True

    ctx['warning_update_available'] = False
    ctx['warning_update_check_active'] = False
    gs = GlobalSettingsObject()
    ctx['global_settings'] = gs.settings
    if request.user.is_staff:
        if gs.settings.update_check_result_warning:
            ctx['warning_update_available'] = True
        if not gs.settings.update_check_ack and 'runserver' not in sys.argv:
            ctx['warning_update_check_active'] = True

    if request.user.is_authenticated:
        ctx['staff_session'] = request.user.has_active_staff_session(request.session.session_key)
        ctx['staff_need_to_explain'] = (
            StaffSession.objects.filter(user=request.user, date_end__isnull=False).filter(
                Q(comment__isnull=True) | Q(comment="")
            )
            if request.user.is_staff and settings.PRETIX_ADMIN_AUDIT_COMMENTS else StaffSession.objects.none()
        )

    return ctx
