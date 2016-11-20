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
    if "HTTP_AUTHORIZATION" not in request.META:
        return unauthed_response()

    method, credentials = request.META["HTTP_AUTHORIZATION"].split(" ", 1)
    if method.lower() != "basic":
        return unauthed_response()

    user, passphrase = credentials.strip().decode("base64").split(":", 1)

    if user != settings.METRICS_USER:
        return unauthed_response()
    if passphrase != settings.METRICS_PASSPHRASE:
        return unauthed_response()

    # ok, the request passed the authentication-barrier, let's hand out the metrics:
    m = metrics.metric_values()

    output = []
    for metric, value in m:
        output.append("{} {}".format(metric, str(value)))

    content = "\n".join(output)

    return HttpResponse(content)
