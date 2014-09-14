from django.conf.urls import patterns, url
from tixlcontrol.views import main

urlpatterns = patterns('',
    url(r'^$', 'tixlcontrol.views.main.index', name='index'),
    url(r'^event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/$', 'tixlcontrol.views.event.index', name='event.index'),
    url(r'^events/$', main.EventList.as_view(), name='events'),
    url(r'^logout$', 'tixlcontrol.views.auth.logout', name='auth.logout'),
    url(r'^login$', 'tixlcontrol.views.auth.login', name='auth.login'),
)
