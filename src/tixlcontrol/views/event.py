from django.shortcuts import render


def index(request, organizer, event):
    return render(request, 'tixlcontrol/event/index.html', {})
