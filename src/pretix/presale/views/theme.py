from django.http import HttpResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_page


@cache_page(3600)
def browserconfig_xml(request):
    return HttpResponse(
        """<?xml version="1.0" encoding="utf-8"?>
<browserconfig>
    <msapplication>
        <tile>
            <square150x150logo src="{}"/>
            <square310x310logo src="{}"/>
            <TileColor>#3b1c4a</TileColor>
        </tile>
    </msapplication>
</browserconfig>""".format(
            static('pretixbase/img/icons/mstile-150x150.png'),
            static('pretixbase/img/icons/mstile-310x310.png'),
        ), content_type='text/xml'
    )


@cache_page(3600)
def webmanifest(request):
    return HttpResponse(
        """{
    "name": "",
    "short_name": "",
    "icons": [
        {
            "src": "%s",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "%s",
            "sizes": "512x512",
            "type": "image/png"
        }
    ],
    "theme_color": "#3b1c4a",
    "background_color": "#3b1c4a",
    "display": "standalone"
}""" % (
            static('pretixbase/img/icons/android-chrome-192x192.png'),
            static('pretixbase/img/icons/android-chrome-512x512.png'),
        ), content_type='text/json'
    )
