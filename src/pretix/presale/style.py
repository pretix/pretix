import hashlib
import logging
import os
from urllib.parse import urljoin, urlsplit

import django_libsass
import sass
from compressor.filters.cssmin import CSSCompressorFilter
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.dispatch import Signal
from django.templatetags.static import static as _static
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Event_SettingsStore, Organizer
from pretix.base.services.tasks import (
    TransactionAwareProfiledEventTask, TransactionAwareTask,
)
from pretix.celery_app import app
from pretix.multidomain.urlreverse import get_domain
from pretix.presale.signals import sass_postamble, sass_preamble

logger = logging.getLogger('pretix.presale.style')
affected_keys = ['primary_font', 'primary_color', 'theme_color_success', 'theme_color_danger']


def compile_scss(object, file="main.scss", fonts=True):
    sassdir = os.path.join(settings.STATIC_ROOT, 'pretixpresale/scss')

    def static(path):
        sp = _static(path)
        if not settings.MEDIA_URL.startswith("/") and sp.startswith("/"):
            domain = get_domain(object.organizer if isinstance(object, Event) else object)
            if domain:
                siteurlsplit = urlsplit(settings.SITE_URL)
                if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                    domain = '%s:%d' % (domain, siteurlsplit.port)
                sp = urljoin('%s://%s' % (siteurlsplit.scheme, domain), sp)
            else:
                sp = urljoin(settings.SITE_URL, sp)
        return '"{}"'.format(sp)

    sassrules = []
    if object.settings.get('primary_color'):
        sassrules.append('$brand-primary: {};'.format(object.settings.get('primary_color')))
    if object.settings.get('theme_color_success'):
        sassrules.append('$brand-success: {};'.format(object.settings.get('theme_color_success')))
    if object.settings.get('theme_color_danger'):
        sassrules.append('$brand-danger: {};'.format(object.settings.get('theme_color_danger')))
    if object.settings.get('theme_color_background'):
        sassrules.append('$body-bg: {};'.format(object.settings.get('theme_color_background')))
    if not object.settings.get('theme_round_borders'):
        sassrules.append('$border-radius-base: 0;')
        sassrules.append('$border-radius-large: 0;')
        sassrules.append('$border-radius-small: 0;')

    font = object.settings.get('primary_font')
    if font != 'Open Sans' and fonts:
        sassrules.append(get_font_stylesheet(font))
        sassrules.append(
            '$font-family-sans-serif: "{}", "Open Sans", "OpenSans", "Helvetica Neue", Helvetica, Arial, sans-serif '
            '!default'.format(
                font
            ))

    if isinstance(object, Event):
        for recv, resp in sass_preamble.send(object, filename=file):
            sassrules.append(resp)

    sassrules.append('@import "{}";'.format(file))

    if isinstance(object, Event):
        for recv, resp in sass_postamble.send(object, filename=file):
            sassrules.append(resp)

    sasssrc = "\n".join(sassrules)
    srcchecksum = hashlib.sha1(sasssrc.encode('utf-8')).hexdigest()

    cp = cache.get_or_set('sass_compile_prefix', now().isoformat())
    css = cache.get('sass_compile_{}_{}'.format(cp, srcchecksum))
    if not css:
        cf = dict(django_libsass.CUSTOM_FUNCTIONS)
        cf['static'] = static
        css = sass.compile(
            string=sasssrc,
            include_paths=[sassdir], output_style='nested',
            custom_functions=cf
        )
        cssf = CSSCompressorFilter(css)
        css = cssf.output()
        cache.set('sass_compile_{}'.format(srcchecksum), css, 3600)

    checksum = hashlib.sha1(css.encode('utf-8')).hexdigest()
    return css, checksum


@app.task(base=TransactionAwareProfiledEventTask)
def regenerate_css(event):
    # main.scss
    css, checksum = compile_scss(event)
    fname = 'pub/{}/{}/presale.{}.css'.format(event.organizer.slug, event.slug, checksum[:16])

    if event.settings.get('presale_css_checksum', '') != checksum:
        newname = default_storage.save(fname, ContentFile(css.encode('utf-8')))
        event.settings.set('presale_css_file', newname)
        event.settings.set('presale_css_checksum', checksum)

    # widget.scss
    css, checksum = compile_scss(event, file='widget.scss', fonts=False)
    fname = 'pub/{}/{}/widget.{}.css'.format(event.organizer.slug, event.slug, checksum[:16])

    if event.settings.get('presale_widget_css_checksum', '') != checksum:
        newname = default_storage.save(fname, ContentFile(css.encode('utf-8')))
        event.settings.set('presale_widget_css_file', newname)
        event.settings.set('presale_widget_css_checksum', checksum)


@app.task(base=TransactionAwareTask)
def regenerate_organizer_css(organizer_id: int):
    organizer = Organizer.objects.get(pk=organizer_id)

    with scope(organizer=organizer):
        # main.scss
        css, checksum = compile_scss(organizer)
        fname = 'pub/{}/presale.{}.css'.format(organizer.slug, checksum[:16])
        if organizer.settings.get('presale_css_checksum', '') != checksum:
            newname = default_storage.save(fname, ContentFile(css.encode('utf-8')))
            organizer.settings.set('presale_css_file', newname)
            organizer.settings.set('presale_css_checksum', checksum)

        # widget.scss
        css, checksum = compile_scss(organizer, file='widget.scss', fonts=False)
        fname = 'pub/{}/widget.{}.css'.format(organizer.slug, checksum[:16])
        if organizer.settings.get('presale_widget_css_checksum', '') != checksum:
            newname = default_storage.save(fname, ContentFile(css.encode('utf-8')))
            organizer.settings.set('presale_widget_css_file', newname)
            organizer.settings.set('presale_widget_css_checksum', checksum)

        non_inherited_events = set(Event_SettingsStore.objects.filter(
            object__organizer=organizer, key__in=affected_keys
        ).values_list('object_id', flat=True))
        for event in organizer.events.all():
            if event.pk not in non_inherited_events:
                regenerate_css.apply_async(args=(event.pk,))


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
        if sty == 'sample':
            continue
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
