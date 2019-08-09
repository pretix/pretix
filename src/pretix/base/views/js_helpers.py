import pycountry
from django.http import JsonResponse

from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS


def states(request):
    cc = request.GET.get("country", "DE")
    if cc not in COUNTRIES_WITH_STATE_IN_ADDRESS:
        return JsonResponse({'data': []})
    types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
    statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
    return JsonResponse({'data': [
        {'name': s.name, 'code': s.code[3:]}
        for s in sorted(statelist, key=lambda s: s.name)
    ]})
