from django.conf.urls import include, url

from .views import abort, success

urlpatterns = [
    url(r'^(?:(?P<organizer>[^/]+)/)?(?P<event>[^/]+)/paypal/', include([
        url(r'^abort/$', abort, name='abort'),
        url(r'^return/$', success, name='return'),
    ])),
]
