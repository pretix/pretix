from django.conf.urls import url, include

from .views import success, abort, retry


urlpatterns = [
    url(r'^paypal/', include([
        url(r'^abort/$', abort, name='abort'),
        url(r'^return/$', success, name='return'),
        url(r'^retry/(?P<order>[^/]+)/', retry, name='retry')
    ])),
]
