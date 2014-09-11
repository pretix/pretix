from django.conf.urls import patterns, url

urlpatterns = patterns('',
    url(r'^$', 'tixlcontrol.views.main.index', name='index'),
    url(r'^logout$', 'tixlcontrol.views.auth.logout', name='auth.logout'),
    url(r'^login$', 'tixlcontrol.views.auth.login', name='auth.login'),
)
