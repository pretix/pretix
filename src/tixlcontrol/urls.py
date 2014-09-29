from django.conf.urls import patterns, url, include
from tixlcontrol.views import main, event, item

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
            'tixlcontrol.views',
            url(r'^$', 'event.index', name='event.index'),
            url(r'^settings$', event.EventUpdate.as_view(), name='event.settings'),
            url(r'^items$', item.ItemList.as_view(), name='event.items'),
            url(r'^items/(?P<item>\d+)/$', item.ItemUpdateGeneral.as_view(), name='event.item'),
            url(r'^items/(?P<item>\d+)/variations$', item.ItemVariations.as_view(), name='event.item.variations'),
            url(r'^categories$', item.CategoryList.as_view(), name='event.items.categories'),
            url(r'^properties$', item.PropertyList.as_view(), name='event.items.properties'),
        )
        ))
)
