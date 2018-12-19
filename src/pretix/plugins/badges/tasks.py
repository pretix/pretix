import logging
from typing import List

from django.core.files.base import ContentFile

from pretix.base.models import (
    CachedFile, Event, OrderPosition, cachedfile_name,
)
from pretix.celery_app import app

from .exporters import render_pdf

logger = logging.getLogger(__name__)


@app.task()
def badges_create_pdf(fileid: int, event: int, positions: List[int]) -> int:
    file = CachedFile.objects.get(id=fileid)
    event = Event.objects.get(id=event)

    pdfcontent = render_pdf(event, OrderPosition.objects.filter(id__in=positions))
    file.file.save(cachedfile_name(file, file.filename), ContentFile(pdfcontent.read()))
    file.save()
    return file.pk
