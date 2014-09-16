from django.conf.urls import patterns, url, include
from tixlcontrol.views import main, event

urlpatterns = patterns('',)
urlpatterns += patterns(
    'tixlcontrol.views.auth',
    url(r'^logout$', 'logout', name='auth.logout'),
    url(r'^login$', 'login', name='auth.login'),
)
urlpatterns += patterns(
    'tixlcontrol.views.main',
    url(r'^$', 'index', name='index'),
    url(r'^events/$', main.EventList.as_view(), name='events'),
)
urlpatterns += patterns(
    'tixlcontrol.views.event',
    url(r'^event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(
        patterns(
            'tixlcontrol.views.event',
            url(r'^$', 'index', name='event.index'),
            url(r'^settings$', event.EventUpdate.as_view(), name='event.settings'),
        )
        ))
)
