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
        resp['Content-Security-Policy'] = "script-src 'unsafe-eval'; style-src 'unsafe-inline'"
        return resp


class PaginationMixin:
    DEFAULT_PAGINATION = 25

    def get_paginate_by(self, queryset):
        skey = 'stored_page_size_' + self.request.resolver_match.url_name
        default = self.request.session.get(skey) or self.paginate_by or self.DEFAULT_PAGINATION
        if self.request.GET.get('page_size'):
            try:
                size = min(250, int(self.request.GET.get("page_size")))
                self.request.session[skey] = size
                return min(250, int(self.request.GET.get("page_size")))
            except ValueError:
                return default
        return default

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_size'] = self.get_paginate_by(None)
        return ctx
