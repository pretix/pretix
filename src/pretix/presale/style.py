import hashlib
import logging
import os
from urllib.parse import urljoin, urlsplit

import django_libsass
import sass
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.dispatch import Signal
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

    sassrules = []
    if event.settings.get('primary_color'):
        sassrules.append('$brand-primary: {};'.format(event.settings.get('primary_color')))

    font = event.settings.get('primary_font')
    if font != 'Open Sans':
        sassrules.append(get_font_stylesheet(font))
        sassrules.append('$font-family-sans-serif: "{}", "Open Sans", "OpenSans", "Helvetica Neue", Helvetica, Arial, sans-serif !default'.format(
            font
        ))

    sassrules.append('@import "main.scss";')

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


register_fonts = Signal()
"""
Return a dictionaries of the following structure. Paths should be relative to static root.

{
    "font name": {
        "regular": {
            "truetype": "….ttf",
            "woff": "…",
            "woff2": "…"
        },
        "bold": {
            ...
        },
        "italic": {
            ...
        },
        "bolditalic": {
            ...
        }
    }
}
"""


def get_fonts():
    f = {}
    for recv, value in register_fonts.send(0):
        f.update(value)
    return f


def get_font_stylesheet(font_name):
    stylesheet = []
    font = get_fonts()[font_name]
    for sty, formats in font.items():
        stylesheet.append('@font-face { ')
        stylesheet.append('font-family: "{}";'.format(font_name))
        if sty in ("italic", "bolditalic"):
            stylesheet.append("font-style: italic;")
        else:
            stylesheet.append("font-style: normal;")
        if sty in ("bold", "bolditalic"):
            stylesheet.append("font-weight: bold;")
        else:
            stylesheet.append("font-weight: normal;")

        srcs = []
        if "woff2" in formats:
            srcs.append("url(static('{}')) format('woff2')".format(formats['woff2']))
        if "woff" in formats:
            srcs.append("url(static('{}')) format('woff')".format(formats['woff']))
        if "truetype" in formats:
            srcs.append("url(static('{}')) format('truetype')".format(formats['truetype']))
        stylesheet.append("src: {};".format(", ".join(srcs)))
        stylesheet.append("}")
    return "\n".join(stylesheet)
