from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.views.generic import View
from django.utils.translation import ugettext_lazy as _

from .event import EventViewMixin


class CartActionMixin:

    def get_success_url(self):
        if "next" in self.request.GET and '://' not in self.request.GET:
            return self.request.GET.get('next')
        else:
            return reverse('presale:event.index', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug,
            })


class CartAdd(EventViewMixin, CartActionMixin, View):

    def post(self, *args, **kwargs):
        messages.error(self.request, _('Cart is not yet implemented'))
        print("hi")
        return redirect(self.get_success_url())
