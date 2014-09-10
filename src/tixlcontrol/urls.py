from django.conf.urls import patterns, url

urlpatterns = patterns('',
    url(r'^$', 'tixlcontrol.views.main.index', name='index'),
)
