from django.conf import settings
from http import HttpResponse
from .. import metrics

unauthedResponse = HttpResponse("<html><title>Forbidden</title><body>You are not authorized to view this page.</body></html>", mimetype="text/html")
unauthedResponse["WWW-Authenticate"] = 'Basic realm="metrics"'
unauthedResponse.status_code = 401


def serve_metrics(request):
    # first check if the user is properly authorized:
    if "HTTP_AUTHORIZATION" not in request.META:
        return unauthedResponse

    method, credentials = request.META["HTTP_AUTHORIZATION"].split(" ", 1)
    if method.lower() != "basic":
        return unauthedResponse

    user, passphrase = credentials.strip().decode("base64").split(":", 1)

    if user != settings.METRICS_USER:
        return unauthedResponse
    if passphrase != settings.METRICS_PASSPHRASE:
        return unauthedResponse

    # ok, the request passed the authentication-barrier, let's hand out the metrics:
    m = metrics.metric_values()

    output = []
    for metric, value in m:
        output.append("{} {}".format(metric, str(value)))

    content = "\n".join(output)

    return HttpResponse(content)
