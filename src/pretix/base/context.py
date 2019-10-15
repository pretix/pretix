import sys

from django.conf import settings


def contextprocessor(request):
    ctx = {
        'rtl': getattr(request, 'LANGUAGE_CODE', 'en') in settings.LANGUAGES_RTL,
    }
    if settings.DEBUG and 'runserver' not in sys.argv:
        ctx['debug_warning'] = True
    elif 'runserver' in sys.argv:
        ctx['development_warning'] = True

    return ctx
