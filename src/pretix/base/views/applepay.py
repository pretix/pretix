from django.http import Http404, HttpResponse

from pretix.base.settings import GlobalSettingsObject


def association(request, *args, **kwargs):
    # This is a crutch to enable event- or organizer-level overrides for the default
    # ApplePay MerchantID domain validation/association file.
    # We do not provide any FormFields for this on purpose!
    #
    # Please refer to https://github.com/pretix/pretix/pull/3611 to get updates on
    # the upcoming and official way to temporarily override the association-file,
    # which will make sure that there are no conflicting requests at the same time.
    #
    # Should you opt to manually inject a different association-file into an organizer
    # or event settings store, we do recommend to remove the setting once you're
    # done and the domain has been validated.
    #
    # If you do not need Stripe's default domain association credential and would
    # rather serve a different default credential, you can do so through the
    # Global Settings editor.
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
