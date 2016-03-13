from django import template
from django.http import Http404
from django.shortcuts import render
from django.views.generic import View

from pretix.base.models import Organizer


class HelpView(View):
    model = Organizer
    context_object_name = 'organizers'
    template_name = 'pretixcontrol/organizers/index.html'
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        try:
            locale = request.LANGUAGE_CODE
            return render(request, 'pretixcontrol/help/%s.%s.html' % (kwargs.get('topic'), locale), {})
        except template.TemplateDoesNotExist:
            try:
                return render(request, 'pretixcontrol/help/%s.html' % kwargs.get('topic'), {})
            except template.TemplateDoesNotExist:
                raise Http404('')
