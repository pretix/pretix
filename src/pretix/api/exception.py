from rest_framework.response import Response
from rest_framework.views import exception_handler, status

from pretix.base.services.locking import LockTimeoutException


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, LockTimeoutException):
        response = Response(
            {'detail': 'The server was too busy to process your request. Please try again.'},
            status=status.HTTP_409_CONFLICT,
            headers={
                'Retry-After': 5
            }
        )

    return response
