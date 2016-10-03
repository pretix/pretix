from debug_toolbar.middleware import DebugToolbarMiddleware
from django.utils.deprecation import MiddlewareMixin


class DebugMiddlewareCompatibilityShim(MiddlewareMixin, DebugToolbarMiddleware):
    pass
