from django.http import HttpResponse

from ..models import User


def healthcheck(request):
    # Perform a simple DB query to see that DB access works
    User.objects.exists()
    return HttpResponse()
