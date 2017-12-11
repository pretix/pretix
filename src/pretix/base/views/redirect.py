import urllib.parse

from django.core import signing
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse


def redir_view(request):
    signer = signing.Signer(salt='safe-redirect')
    try:
        url = signer.unsign(request.GET.get('url', ''))
    except signing.BadSignature:
        return HttpResponseBadRequest('Invalid parameter')
    r = HttpResponseRedirect(url)
    r['X-Robots-Tag'] = 'noindex'
    return r


def safelink(url):
    signer = signing.Signer(salt='safe-redirect')
    return reverse('redirect') + '?url=' + urllib.parse.quote(signer.sign(url))
