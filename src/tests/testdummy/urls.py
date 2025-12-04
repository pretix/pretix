from django.http import HttpResponse
from django.urls import path


def view(request):
    return HttpResponse("")


urlpatterns = [
    path(
        "testdummy",
        view,
        name="view",
    ),
]

organizer_patterns = [
    path(
        "testdummy",
        view,
        name="view",
    ),
]

event_patterns = [
    path(
        "testdummy",
        view,
        name="view",
    ),
]
