from django.shortcuts import render


def index(request, event):
    return render(request, 'tixlcontrol/event/index.html', {})
