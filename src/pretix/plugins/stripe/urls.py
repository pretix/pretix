from django.conf.urls import url, include

from .views import webhook


urlpatterns = [
    url(r'^stripe/', include([
        url(r'^webhook/$', webhook, name='webhook'),
    ])),
]
