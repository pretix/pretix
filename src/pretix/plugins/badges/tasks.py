import logging
from typing import List

from django.core.files.base import ContentFile

from pretix.base.models import (
    CachedFile, Event, OrderPosition, cachedfile_name,
)
from pretix.base.services.orders import OrderError
from pretix.base.services.tasks import EventTask
from pretix.celery_app import app

from .exporters import render_pdf

logger = logging.getLogger(__name__)


@app.task(base=EventTask, throws=(OrderError,))
def badges_create_pdf(event: Event, fileid: int, positions: List[int]) -> int:
    file = CachedFile.objects.get(id=fileid)

    pdfcontent = render_pdf(event, OrderPosition.objects.filter(id__in=positions))
    file.file.save(cachedfile_name(file, file.filename), ContentFile(pdfcontent.read()))
    file.save()
    return file.pk
