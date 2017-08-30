from django.http import (
    HttpResponseForbidden, HttpResponseNotFound, HttpResponseServerError,
)
from django.middleware.csrf import REASON_NO_CSRF_COOKIE, REASON_NO_REFERER
from django.template import TemplateDoesNotExist, loader
from django.template.loader import get_template
from django.utils.functional import Promise
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import requires_csrf_token


def csrf_failure(request, reason=""):
    t = get_template('csrffail.html')
    c = {
        'reason': reason,
        'no_referer': reason == REASON_NO_REFERER,
        'no_referer1': _(
            "You are seeing this message because this HTTPS site requires a "
            "'Referer header' to be sent by your Web browser, but none was "
            "sent. This header is required for security reasons, to ensure "
            "that your browser is not being hijacked by third parties."),
        'no_referer2': _(
            "If you have configured your browser to disable 'Referer' headers, "
            "please re-enable them, at least for this site, or for HTTPS "
            "connections, or for 'same-origin' requests."),
        'no_cookie': reason == REASON_NO_CSRF_COOKIE,
        'no_cookie1': _(
            "You are seeing this message because this site requires a CSRF "
            "cookie when submitting forms. This cookie is required for "
            "security reasons, to ensure that your browser is not being "
            "hijacked by third parties."),
        'no_cookie2': _(
            "If you have configured your browser to disable cookies, please "
            "re-enable them, at least for this site, or for 'same-origin' "
            "requests."),
    }
    return HttpResponseForbidden(t.render(c), content_type='text/html')


@requires_csrf_token
def page_not_found(request, exception):
    exception_repr = exception.__class__.__name__
    # Try to get an "interesting" exception message, if any (and not the ugly
    # Resolver404 dictionary)
    try:
        message = exception.args[0]
    except (AttributeError, IndexError):
        pass
    else:
        if isinstance(message, str) or isinstance(message, Promise):
            exception_repr = str(message)
    context = {
        'request_path': request.path,
        'exception': exception_repr,
    }
    template = get_template('404.html')
    body = template.render(context, request)
    return HttpResponseNotFound(body)


@requires_csrf_token
def server_error(request):
    try:
        template = loader.get_template('500.html')
    except TemplateDoesNotExist:
        return HttpResponseServerError('<h1>Server Error (500)</h1>', content_type='text/html')
    return HttpResponseServerError(template.render({
        'request': request
    }))
