#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views.generic import FormView

from pretix.base.models.event import SubEvent
from pretix.base.templatetags.urlreplace import url_replace
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin

from ...base.i18n import get_language_without_region
from ...base.models import Item, ItemVariation, WaitingListEntry
from ..forms.waitinglist import WaitingListForm
from . import allow_frame_if_namespaced


@method_decorator(allow_frame_if_namespaced, 'dispatch')
class WaitingView(EventViewMixin, FormView):
    template_name = 'pretixpresale/event/waitinglist.html'
    form_class = WaitingListForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        kwargs['instance'] = WaitingListEntry(
            item=self.item_and_variation[0], variation=self.item_and_variation[1],
            event=self.request.event, locale=get_language_without_region(),
            subevent=self.subevent
        )
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.request.event
        ctx['subevent'] = self.subevent
        ctx['item'], ctx['variation'] = self.item_and_variation
        return ctx

    def get(self, request, *args, **kwargs):
        if request.GET.get('iframe', '') == '1' and 'require_cookie' not in request.GET:
            # Widget just opened. Let's to a stupid redirect to check if cookies are disabled
            return redirect(request.get_full_path() + '&require_cookie=true')
        elif 'require_cookie' in request.GET and settings.SESSION_COOKIE_NAME not in request.COOKIES:
            # Cookies are in fact not supported. We can't even display the form, since we can't get CSRF right without
            # cookies.
            r = render(request, 'pretixpresale/event/cookies.html', {
                'url': eventreverse(
                    request.event, "presale:event.waitinglist", kwargs={'cart_namespace': kwargs.get('cart_namespace')}
                ) + '?' + url_replace(request, 'require_cookie', '', 'iframe', '')
            })
            r._csp_ignore = True
            return r

        return super().get(request, *args, **kwargs)

    @cached_property
    def item_and_variation(self):
        try:
            item = self.request.event.items.get(pk=self.request.GET.get('item'))
            if 'var' in self.request.GET:
                var = item.variations.get(pk=self.request.GET['var'])
            elif item.has_variations:
                return None
            else:
                var = None
            return item, var
        except (Item.DoesNotExist, ItemVariation.DoesNotExist, ValueError):
            return None

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        if not self.request.event.settings.waiting_list_enabled:
            messages.error(request, _("Waiting lists are disabled for this event."))
            return redirect(self.get_index_url())

        if not self.item_and_variation:
            messages.error(request, _("We could not identify the product you selected."))
            return redirect(self.get_index_url())

        if not self.item_and_variation[0].allow_waitinglist:
            messages.error(request, _("The waiting list is disabled for this product."))
            return redirect(self.get_index_url())

        self.subevent = None
        if request.event.has_subevents:
            if 'subevent' in request.GET:
                self.subevent = get_object_or_404(SubEvent, event=request.event, pk=request.GET['subevent'],
                                                  active=True)
            else:
                messages.error(request, pgettext_lazy('subevent', "You need to select a date."))
                return redirect(self.get_index_url())

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        availability = (
            self.item_and_variation[1].check_quotas(count_waitinglist=True, subevent=self.subevent)
            if self.item_and_variation[1]
            else self.item_and_variation[0].check_quotas(count_waitinglist=True, subevent=self.subevent)
        )
        if availability[0] == 100:
            messages.error(self.request, _("You cannot add yourself to the waiting list as this product is currently "
                                           "available."))
            return redirect(self.get_index_url())

        form.save()
        messages.success(self.request, _("We've added you to the waiting list. You will receive "
                                         "an email as soon as tickets get available again."))
        return super().form_valid(form)

    def get_success_url(self):
        return self.get_index_url()
