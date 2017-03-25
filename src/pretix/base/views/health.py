from django.conf import settings
from django.core import cache
from django.http import HttpResponse

from ..models import User


def healthcheck(request):
    # Perform a simple DB query to see that DB access works
    User.objects.exists()

    # Test if redis access works
    if settings.HAS_REDIS:
        import django_redis

        redis = django_redis.get_redis_connection("redis")
        redis.set("_healthcheck", 1)
        if not redis.exists("_healthcheck"):
            return HttpResponse("Redis not available.", status=503)

    cache.cache.set("_healthcheck", "1")
    if not cache.cache.get("_healthcheck") == "1":
        return HttpResponse("Cache not available.", status=503)

    return HttpResponse()
