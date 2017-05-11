from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/editor/$', views.EditorView.as_view(),
        name='editor'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/editor/webfonts.css',
        views.FontsCSSView.as_view(),
        name='css'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/editor/(?P<filename>[^/]+).pdf$',
        views.PdfView.as_view(), name='pdf'),
]
