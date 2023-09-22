from django.http import Http404, HttpResponse

from pretix.base.settings import GlobalSettingsObject


def association(request, *args, **kwargs):
    if hasattr(request, 'event'):
        settings = request.event.settings
    elif hasattr(request, 'organizer'):
        settings = request.organizer.settings
    else:
        settings = GlobalSettingsObject().settings

    if not settings.get('apple_domain_association', None):
        raise Http404('')
    else:
        return HttpResponse(settings.get('apple_domain_association'))
