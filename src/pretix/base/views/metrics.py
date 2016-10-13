from http import HttpResponse
from .. import metrics


def serve_metrics(request):
    m = metrics.metric_values()

    output = []
    for metric, value in m:
        output.append("{} {}".format(metric, str(value)))

    content = "\n".join(output)

    return HttpResponse(content)
