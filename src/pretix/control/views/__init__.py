from django.views.generic import edit


class EventBasedFormMixin:

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if hasattr(self.request, 'event'):
            kwargs['event'] = self.request.event
        return kwargs


class CreateView(EventBasedFormMixin, edit.CreateView):
    """
    Like Django's default CreateView, but passes the optional event
    argument to the form. This is necessary for I18nModelForms to work
    properly.
    """
    pass


class UpdateView(EventBasedFormMixin, edit.UpdateView):
    """
    Like Django's default UpdateView, but passes the optional event
    argument to the form. This is necessary for I18nModelForms to work
    properly.
    """
    pass


class ChartContainingView:

    def get(self, request, *args, **kwargs):
        resp = super().get(request, *args, **kwargs)
        # required by raphael.js
        resp['Content-Security-Policy'] = "script-src {static} 'unsafe-eval'; style-src {static} 'unsafe-inline'"
        return resp
