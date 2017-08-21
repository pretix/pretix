import hashlib
import logging
import os
from urllib.parse import urljoin, urlsplit

import django_libsass
import sass
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.templatetags.static import static as _static

from pretix.base.models import Event
from pretix.base.services.async import ProfiledTask
from pretix.celery_app import app
from pretix.multidomain.urlreverse import get_domain

logger = logging.getLogger('pretix.presale.style')


@app.task(base=ProfiledTask)
def regenerate_css(event_id: int):
    event = Event.objects.select_related('organizer').get(pk=event_id)
    sassdir = os.path.join(settings.STATIC_ROOT, 'pretixpresale/scss')

    sassrules = []
    if event.settings.get('primary_color'):
        sassrules.append('$brand-primary: {};'.format(event.settings.get('primary_color')))
    sassrules.append('@import "main.scss";')

    def static(path):
        sp = _static(path)
        if not settings.MEDIA_URL.startswith("/") and sp.startswith("/"):
            domain = get_domain(event.organizer)
            if domain:
                siteurlsplit = urlsplit(settings.SITE_URL)
                if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                    domain = '%s:%d' % (domain, siteurlsplit.port)
                sp = urljoin('%s://%s' % (siteurlsplit.scheme, domain), sp)
            else:
                sp = urljoin(settings.SITE_URL, sp)
        return '"{}"'.format(sp)

    cf = dict(django_libsass.CUSTOM_FUNCTIONS)
    cf['static'] = static
    css = sass.compile(
        string="\n".join(sassrules),
        include_paths=[sassdir], output_style='compressed',
        custom_functions=cf
    )
    checksum = hashlib.sha1(css.encode('utf-8')).hexdigest()
    fname = '{}/{}/presale.{}.css'.format(
        event.organizer.slug, event.slug, checksum[:16]
    )

    if event.settings.get('presale_css_checksum', '') != checksum:
        newname = default_storage.save(fname, ContentFile(css.encode('utf-8')))
        event.settings.set('presale_css_file', newname)
        event.settings.set('presale_css_checksum', checksum)
