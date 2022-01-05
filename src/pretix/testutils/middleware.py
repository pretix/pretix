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
        return self.get_response(request)
