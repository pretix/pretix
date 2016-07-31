from django.conf.urls import include, url

from .views import abort, success

event_patterns = [
    url(r'^paypal/', include([
        url(r'^abort/$', abort, name='abort'),
        url(r'^return/$', success, name='return'),
    ])),
]
