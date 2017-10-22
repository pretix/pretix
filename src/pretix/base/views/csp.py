import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger('pretix.security.csp')


@csrf_exempt
def csp_report(request):
    try:
        body = json.loads(request.body.decode())
        logger.warning(
            'CSP violation at {r[document-uri]}\n'
            'Referer: {r[referrer]}\n'
            'Blocked: {r[blocked-uri]}\n'
            'Violated: {r[violated-directive]}\n'
            'Original polity: {r[original-policy]}'.format(r=body['csp-report'])
        )
    except (ValueError, KeyError) as e:
        logger.exception('CSP report failed ' + str(e))
        return HttpResponseBadRequest()
    return HttpResponse()
