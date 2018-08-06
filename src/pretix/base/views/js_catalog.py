from django.utils import timezone
from django.utils.translation.trans_real import DjangoTranslation
from django.views.decorators.cache import cache_page
from django.views.decorators.http import etag
from django.views.i18n import JavaScriptCatalog, render_javascript_catalog

# Yes, we want to regenerate this every time the module has been imported to
# refresh the cache at least at every code deployment
import_date = timezone.now().strftime("%Y%m%d%H%M")


# This is not a valid Django URL configuration, as the final
# configuration is done by the pretix.multidomain package.
js_info_dict = {
    'packages': ('pretix',),
}


@etag(lambda *s, **k: import_date)
@cache_page(3600, key_prefix='js18n-%s' % import_date)
def js_catalog(request, lang):
    c = JavaScriptCatalog()
    c.translation = DjangoTranslation(lang, domain='djangojs')
    return render_javascript_catalog(c.get_catalog(), c.get_plural())
