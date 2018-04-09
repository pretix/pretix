from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/editor/$', views.EditorView.as_view(),
        name='editor'),
]
