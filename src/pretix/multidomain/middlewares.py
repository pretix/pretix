import time
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.sessions.middleware import \
    SessionMiddleware as BaseSessionMiddleware
from django.core.exceptions import DisallowedHost
from django.http.request import split_domain_port
from django.middleware.csrf import CsrfViewMiddleware as BaseCsrfMiddleware
from django.utils.cache import patch_vary_headers
from django.utils.http import cookie_date

from pretix.multidomain.models import KnownDomain


class MultiDomainMiddleware:
    def process_request(self, request):
        # We try three options, in order of decreasing preference.
        if settings.USE_X_FORWARDED_HOST and ('HTTP_X_FORWARDED_HOST' in request.META):
            host = request.META['HTTP_X_FORWARDED_HOST']
        elif 'HTTP_HOST' in request.META:
            host = request.META['HTTP_HOST']
        else:
            # Reconstruct the host using the algorithm from PEP 333.
            host = request.META['SERVER_NAME']
            server_port = str(request.META['SERVER_PORT'])
            if server_port != ('443' if request.is_secure() else '80'):
                host = '%s:%s' % (host, server_port)

        domain, port = split_domain_port(host)
        default_domain, default_port = split_domain_port(urlparse(settings.SITE_URL).netloc)
        if domain:
            request.host = domain
            request.port = int(port) if port else None
            try:
                kd = KnownDomain.objects.get(domainname=domain)  # noqa
                request.domain = kd
            except:
                if settings.DEBUG or domain in ('testserver', 'localhost') or domain == default_domain:
                    return  # TODO: Select main page
                raise DisallowedHost("Unknown host: %r" % host)
            else:
                request.organizer = kd.organizer
        else:
            raise DisallowedHost("Invalid HTTP_HOST header: %r." % host)


class SessionMiddleware(BaseSessionMiddleware):
    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            pass
        else:
            # First check if we need to delete this cookie.
            # The session should be deleted only if the session is entirely empty
            if settings.SESSION_COOKIE_NAME in request.COOKIES and empty:
                response.delete_cookie(settings.SESSION_COOKIE_NAME)
            else:
                if accessed:
                    patch_vary_headers(response, ('Cookie',))
                if modified or settings.SESSION_SAVE_EVERY_REQUEST:
                    if request.session.get_expire_at_browser_close():
                        max_age = None
                        expires = None
                    else:
                        max_age = request.session.get_expiry_age()
                        expires_time = time.time() + max_age
                        expires = cookie_date(expires_time)
                    # Save the session data and refresh the client cookie.
                    # Skip session save for 500 responses, refs #3881.
                    if response.status_code != 500:
                        request.session.save()
                        response.set_cookie(settings.SESSION_COOKIE_NAME,
                                            request.session.session_key, max_age=max_age,
                                            expires=expires, domain=request.host,
                                            path=settings.SESSION_COOKIE_PATH,
                                            secure=request.scheme == 'https',
                                            httponly=settings.SESSION_COOKIE_HTTPONLY or None)
        return response


class CsrfViewMiddleware(BaseCsrfMiddleware):
    def process_response(self, request, response):
        if getattr(response, 'csrf_processing_done', False):
            return response

        # If CSRF_COOKIE is unset, then CsrfViewMiddleware.process_view was
        # never called, probably because a request middleware returned a response
        # (for example, contrib.auth redirecting to a login page).
        if request.META.get("CSRF_COOKIE") is None:
            return response

        if not request.META.get("CSRF_COOKIE_USED", False):
            return response

        # Set the CSRF cookie even if it's already set, so we renew
        # the expiry timer.
        response.set_cookie(settings.CSRF_COOKIE_NAME,
                            request.META["CSRF_COOKIE"],
                            max_age=settings.CSRF_COOKIE_AGE,
                            domain=request.host,
                            path=settings.CSRF_COOKIE_PATH,
                            secure=request.scheme == 'https',
                            httponly=settings.CSRF_COOKIE_HTTPONLY
                            )
        # Content varies with the CSRF cookie, so set the Vary header.
        patch_vary_headers(response, ('Cookie',))
        response.csrf_processing_done = True
        return response
