import base64
import hmac

from django.conf import settings
from django.http import HttpResponse

from .. import metrics


def unauthed_response():
    content = "<html><title>Forbidden</title><body>You are not authorized to view this page.</body></html>"
    response = HttpResponse(content, content_type="text/html")
    response["WWW-Authenticate"] = 'Basic realm="metrics"'
    response.status_code = 401
    return response


def serve_metrics(request):
    if not settings.METRICS_ENABLED:
        return unauthed_response()

    # check if the user is properly authorized:
    if "Authorization" not in request.headers:
        return unauthed_response()

    method, credentials = request.headers["Authorization"].split(" ", 1)
    if method.lower() != "basic":
        return unauthed_response()

    user, passphrase = base64.b64decode(credentials.strip()).decode().split(":", 1)

    if not hmac.compare_digest(user, settings.METRICS_USER):
        return unauthed_response()
    if not hmac.compare_digest(passphrase, settings.METRICS_PASSPHRASE):
        return unauthed_response()

    # ok, the request passed the authentication-barrier, let's hand out the metrics:
    m = metrics.metric_values()

    output = []
    for metric, sub in m.items():
        for label, value in sub.items():
            output.append("{}{} {}".format(metric, label, str(value)))

    content = "\n".join(output) + "\n"

    return HttpResponse(content)
