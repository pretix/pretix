from django.conf.urls import patterns, url, include

import pretixpresale.views.event
import pretixpresale.views.cart

urlpatterns = patterns(
    '',
    url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(
        patterns(
            'pretixpresale.views.event',
            url(r'^$', pretixpresale.views.event.EventIndex.as_view(), name='event.index'),
            url(r'^cart/add$', pretixpresale.views.cart.CartAdd.as_view(), name='event.cart.add'),
        )
    )),
)
