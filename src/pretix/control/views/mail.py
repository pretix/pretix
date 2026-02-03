#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import base64
import logging
from email.header import decode_header, make_header
from email.utils import parseaddr

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import BadRequest
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import ngettext
from django.views import View
from django.views.generic import DetailView, ListView

from pretix.base.middleware import _merge_csp, _parse_csp, _render_csp
from pretix.base.models import OutgoingMail
from pretix.base.services.mail import mail_send_task
from pretix.control.forms.filter import OutgoingMailFilterForm
from pretix.control.permissions import OrganizerPermissionRequiredMixin
from pretix.control.views.organizer import OrganizerDetailViewMixin

logger = logging.getLogger(__name__)


class OutgoingMailQueryMixin:

    @cached_property
    def request_data(self):
        if self.request.method == "POST":
            d = self.request.POST
        else:
            d = self.request.GET
        d = d.copy()
        return d

    @cached_property
    def filter_form(self):
        return OutgoingMailFilterForm(
            data=self.request_data,
            request=self.request,
        )

    def get_queryset(self):
        qs = self.request.organizer.outgoing_mails.select_related(
            'event', 'order', 'orderposition', 'customer'
        )

        if 'outgoingmail' in self.request_data and '__ALL' not in self.request_data:
            qs = qs.filter(
                id__in=self.request_data.getlist('outgoingmail')
            )
        elif self.request.method == 'GET' or '__ALL' in self.request_data:
            if self.filter_form.is_valid():
                qs = self.filter_form.filter_qs(qs)
        else:
            raise BadRequest("No mails selected")

        return qs


class OutgoingMailListView(OutgoingMailQueryMixin, OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = OutgoingMail
    template_name = 'pretixcontrol/organizers/outgoing_mails.html'
    # Assume "the highest" permission level for now because emails could belog to any event, order, or customer.
    # We plan to add a special permissoin in the future
    permission = 'can_change_organizer_settings'
    context_object_name = 'mails'
    paginate_by = 100

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        ctx['days'] = int(settings.OUTGOING_MAIL_RETENTION / (24 * 3600))
        return ctx


class OutgoingMailDetailView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    model = OutgoingMail
    template_name = 'pretixcontrol/organizers/outgoing_mail.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'mail'

    def get_object(self, queryset=None):
        return get_object_or_404(OutgoingMail, organizer=self.request.organizer, pk=self.kwargs.get('mail'))

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if 'Content-Security-Policy' in response:
            h = _parse_csp(response['Content-Security-Policy'])
        else:
            h = {}
        csps = {
            'frame-src': ['data:'],
            # Unfortuantely, we can't avoid unsafe-inline for style here.
            # See outgoingmail.js for the protection measures we take.
            'style-src': ["'unsafe-inline'"],
        }
        _merge_csp(h, csps)
        response['Content-Security-Policy'] = _render_csp(h)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.object.body_html:
            ctx['data_url'] = "data:text/html;charset=utf-8;base64," + base64.b64encode(self.object.body_html.encode()).decode()

        from_name, from_email = parseaddr(self.object.sender)
        if from_name:
            from_name = make_header(decode_header(from_name))
        ctx['sender'] = "{} <{}>".format(from_name, from_email) if from_name else from_email

        return ctx


class OutgoingMailBulkAction(OutgoingMailQueryMixin, OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, View):
    permission = 'can_change_organizer_settings'

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'retry':
            ids = set(
                self.get_queryset().filter(status__in=OutgoingMail.STATUS_LIST_RETRYABLE).values_list("pk", flat=True)
            )
            with transaction.atomic():
                OutgoingMail.objects.filter(pk__in=ids).update(
                    status=OutgoingMail.STATUS_QUEUED,
                    sent=None,
                )
                self.request.organizer.log_action(
                    'pretix.organizer.outgoingmails.retried', user=self.request.user, data={
                        'mails': list(ids)
                    }, save=False
                )
            for i in ids:
                mail_send_task.apply_async(kwargs={"outgoing_mail": i})

            messages.success(request, ngettext(
                "A retry of one email was scheduled.",
                "A retry of {num} emails was scheduled.",
                len(ids),
            ).format(num=len(ids)))
        elif request.POST.get('action') == 'abort':
            ids = set(
                self.get_queryset().filter(
                    status__in=(OutgoingMail.STATUS_QUEUED, OutgoingMail.STATUS_AWAITING_RETRY)
                ).values_list("pk", flat=True)
            )
            with transaction.atomic():
                OutgoingMail.objects.filter(pk__in=ids).update(
                    status=OutgoingMail.STATUS_ABORTED,
                    sent=None,
                )
                self.request.organizer.log_action(
                    'pretix.organizer.outgoingmails.aborted', user=self.request.user, data={
                        'mails': list(ids)
                    }, save=False
                )
            for i in ids:
                mail_send_task.apply_async(kwargs={"outgoing_mail": i})

            messages.success(request, ngettext(
                "One email was aborted and will not be sent.",
                "{num} emails were aborted and will not be sent.",
                len(ids),
            ).format(num=len(ids)))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:organizer.outgoingmails', kwargs={
            'organizer': self.request.organizer.slug,
        })
