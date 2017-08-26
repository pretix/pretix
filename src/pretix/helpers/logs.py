import logging

from django.conf import settings


class AdminExistsFilter(logging.Filter):
    def filter(self, record):
        return not settings.DEBUG and len(settings.ADMINS) > 0
