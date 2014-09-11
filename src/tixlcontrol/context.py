from django.conf import settings

def contextprocessor(request):
    return {
        'settings': settings,
    }
