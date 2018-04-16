from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView

from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.plugins.badges.forms import BadgeLayoutForm

from .models import BadgeLayout


class LayoutListView(EventPermissionRequiredMixin, ListView):
    model = BadgeLayout
    permission = ('can_change_event_settings', 'can_view_orders')
    template_name = 'pretixplugins/badges/index.html'
    context_object_name = 'layouts'

    def get_queryset(self):
        return self.request.event.badge_layouts.all()


class LayoutCreate(EventPermissionRequiredMixin, CreateView):
    model = BadgeLayout
    form_class = BadgeLayoutForm
    template_name = 'pretixplugins/badges/edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'layout'

    def get_success_url(self) -> str:
        return reverse('plugins:badges:index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        if not self.request.event.badge_layouts.filter(default=True).exists():
            form.instance.default = True
        messages.success(self.request, _('The new badge layout has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.plugins.badges.layout.added', user=self.request.user, data=dict(form.cleaned_data))
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)


class LayoutSetDefault(EventPermissionRequiredMixin, DetailView):
    model = BadgeLayout
    permission = 'can_change_event_settings'

    def get_object(self, queryset=None) -> BadgeLayout:
        try:
            return self.request.event.badge_layouts.get(
                id=self.kwargs['layout']
            )
        except BadgeLayout.DoesNotExist:
            raise Http404(_("The requested badge layout does not exist."))

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        messages.success(self.request, _('Your changes have been saved.'))
        obj = self.get_object()
        self.request.event.badge_layouts.exclude(pk=obj.pk).update(default=False)
        obj.default = True
        obj.save(update_fields=['default'])
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('plugins:badges:index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class LayoutDelete(EventPermissionRequiredMixin, DeleteView):
    model = BadgeLayout
    template_name = 'pretixplugins/badges/delete.html'
    permission = 'can_change_event_settings'
    context_object_name = 'layout'

    def get_object(self, queryset=None) -> BadgeLayout:
        try:
            return self.request.event.badge_layouts.get(
                id=self.kwargs['layout']
            )
        except BadgeLayout.DoesNotExist:
            raise Http404(_("The requested badge layout does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.log_action(action='pretix.plugins.badges.layout.deleted', user=request.user)
        self.object.delete()
        if not self.request.event.badge_layouts.filter(default=True).exists():
            f = self.request.event.badge_layouts.first()
            if f:
                f.default = True
                f.save(update_fields=['default'])
        messages.success(self.request, _('The selected badge layout been deleted.'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('plugins:badges:index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class LayoutEditorView(View):
    pass
