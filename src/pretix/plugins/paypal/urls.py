from django.conf.urls import include, url

from .views import abort, retry, success

urlpatterns = [
    url(r'^paypal/', include([
        url(r'^abort/$', abort, name='abort'),
        url(r'^return/$', success, name='return'),
        url(r'^retry/(?P<order>[^/]+)/', retry, name='retry')
    ])),
]
