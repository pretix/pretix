from django.conf import settings
from django.core.urlresolvers import resolve
from django.utils.encoding import force_str
from django.utils.six.moves.urllib.parse import urlparse
from django.shortcuts import resolve_url
from django.contrib.auth import REDIRECT_FIELD_NAME


class LoginRequiredMiddleware:

    """
    This middleware enforces all requests to the control app
    to require login.
    """

    EXCEPTIONS = (
        "login"
    )

    def process_request(self, request):
        if not request.user.is_authenticated():
            url_namespace = resolve(request.path_info).namespace
            url_name = resolve(request.path_info).url_name
            if url_namespace == 'control' and url_name not in self.EXCEPTIONS:
                # Taken from django/contrib/auth/decorators.py
                path = request.build_absolute_uri()
                # urlparse chokes on lazy objects in Python 3, force to str
                resolved_login_url = force_str(
                    resolve_url(settings.LOGIN_URL_CONTROL))
                # If the login url is the same scheme and net location then just
                # use the path as the "next" url.
                login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
                current_scheme, current_netloc = urlparse(path)[:2]
                if ((not login_scheme or login_scheme == current_scheme) and
                        (not login_netloc or login_netloc == current_netloc)):
                    path = request.get_full_path()
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(
                    path, resolved_login_url, REDIRECT_FIELD_NAME)
