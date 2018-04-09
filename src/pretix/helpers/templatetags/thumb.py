import logging

from django import template
from django.core.files import File
from django.core.files.storage import default_storage

from pretix.helpers.thumb import get_thumbnail

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def thumb(source, arg):
    if isinstance(source, File):
        source = source.name
    try:
        return get_thumbnail(source, arg).thumb.url
    except:
        logger.exception('Failed to create thumbnail')
        return default_storage.url(source)
