from django.conf import settings


def build_absolute_uri(url):
    return settings.SITE_URL + url
