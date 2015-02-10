from django.conf.urls import patterns, url, include

import pretixpresale.views.event

urlpatterns = patterns('',)
urlpatterns += patterns(
    'pretixpresale.views.event',
    url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(
        patterns(
            'pretixpresale.views',
            url(r'^$', pretixpresale.views.event.EventIndex.as_view(), name='event.index'),
        )
    ))
)
