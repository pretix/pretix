import threading

storage = threading.local()
storage.debugflags = []


class DebugFlagMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '_debug_flag' in request.GET:
            storage.debugflags = request.GET.getlist('_debug_flag')
        else:
            storage.debugflags = []

        if 'skip-csrf' in storage.debugflags:
            request.csrf_processing_done = True

        return self.get_response(request)
