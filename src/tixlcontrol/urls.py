from django.conf.urls import patterns, url
from tixlcontrol.views import main, event

urlpatterns = patterns('',
    url(r'^$', 'tixlcontrol.views.main.index', name='index'),
    url(r'^event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/$', 'tixlcontrol.views.event.index', name='event.index'),
    url(r'^event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings$', event.EventUpdate.as_view(), name='event.settings'),
    url(r'^events/$', main.EventList.as_view(), name='events'),
    url(r'^logout$', 'tixlcontrol.views.auth.logout', name='auth.logout'),
    url(r'^login$', 'tixlcontrol.views.auth.login', name='auth.login'),
)
