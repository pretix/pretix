import hashlib
import logging
import os

import django_libsass
import sass
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from pretix.base.models import Event
from pretix.base.services.async import ProfiledTask
from pretix.celery_app import app

logger = logging.getLogger('pretix.presale.style')


@app.task(base=ProfiledTask)
def regenerate_css(event_id: int):
    event = Event.objects.select_related('organizer').get(pk=event_id)
    sassdir = os.path.join(settings.STATIC_ROOT, 'pretixpresale/scss')

    sassrules = [
        '$brand-primary: {};'.format(event.settings.get('primary_color')),
        '@import "main.scss";',
    ]

    css = sass.compile(
        string="\n".join(sassrules),
        include_paths=[sassdir], output_style='compressed',
        custom_functions=django_libsass.CUSTOM_FUNCTIONS
    )
    checksum = hashlib.sha1(css.encode('utf-8')).hexdigest()
    fname = '{}/{}/presale.{}.css'.format(
        event.organizer.slug, event.slug, checksum[:16]
    )

    if event.settings.get('presale_css_checksum', '') != checksum:
        newname = default_storage.save(fname, ContentFile(css.encode('utf-8')))
        event.settings.set('presale_css_file', newname)
        event.settings.set('presale_css_checksum', checksum)
