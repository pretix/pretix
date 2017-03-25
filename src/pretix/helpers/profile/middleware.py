import cProfile
import os
import random
import time

from django.conf import settings


class CProfileMiddleware(object):
    blacklist = (
        '/healthcheck/',
        '/jsi18n/'
    )

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        for b in self.blacklist:
            if b in request.path:
                return self.get_response(request)

        if settings.PROFILING_RATE > 0 and random.random() < settings.PROFILING_RATE / 100:
            profiler = cProfile.Profile()
            profiler.enable()
            starttime = time.perf_counter()
            response = self.get_response(request)
            profiler.disable()
            tottime = time.perf_counter() - starttime
            profiler.dump_stats(os.path.join(settings.PROFILE_DIR, '{time:.0f}_{tottime:.3f}_{path}.pstat'.format(
                path=request.path[1:].replace("/", "_"), tottime=tottime, time=time.time()
            )))
            return response
        else:
            return self.get_response(request)
