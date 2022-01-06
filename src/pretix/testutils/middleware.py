import threading

from django.conf import settings
from django.db import connection

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

        if 'repeatable-read' in storage.debugflags:
            with connection.cursor() as cursor:
                if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                    cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ;')
                elif 'mysql' in settings.DATABASES['default']['ENGINE']:
                    cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;')

        try:
            return self.get_response(request)
        finally:
            if 'repeatable-read' in storage.debugflags:
                with connection.cursor() as cursor:
                    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                        cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED;')
                    elif 'mysql' in settings.DATABASES['default']['ENGINE']:
                        cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;')
