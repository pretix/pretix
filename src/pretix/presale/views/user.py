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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from pretix.base.email import get_email_context
from pretix.base.services.mail import INVALID_ADDRESS, SendMailException, mail
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.user import ResendLinkForm
from pretix.presale.views import EventViewMixin


class ResendLinkView(EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/resend_link.html'

    @cached_property
    def link_form(self):
        return ResendLinkForm(data=self.request.POST if self.request.method == 'POST' else None)

    def post(self, request, *args, **kwargs):
        if not self.link_form.is_valid():
            messages.error(self.request, _('We had difficulties processing your input.'))
            return self.get(request, *args, **kwargs)

        user = self.link_form.cleaned_data.get('email')

        if settings.HAS_REDIS:
            from django_redis import get_redis_connection
            rc = get_redis_connection("redis")
            if rc.exists('pretix_resend_{}_{}'.format(request.event.pk, user)):
                messages.error(request, _('If the email address you entered is valid and associated with a ticket, we have '
                                          'already sent you an email with a link to your ticket in the past {number} hours. '
                                          'If the email did not arrive, please check your spam folder and also double check '
                                          'that you used the correct email address.').format(number=24))
                return redirect(eventreverse(self.request.event, 'presale:event.resend_link'))
            else:
                rc.setex('pretix_resend_{}_{}'.format(request.event.pk, user), 3600 * 24, '1')

        orders = self.request.event.orders.filter(email__iexact=user)

        if not orders:
            user = INVALID_ADDRESS

        subject = self.request.event.settings.mail_subject_resend_all_links
        template = self.request.event.settings.mail_text_resend_all_links
        context = get_email_context(event=self.request.event, orders=orders)
        try:
            mail(user, subject, template, context, event=self.request.event, locale=self.request.LANGUAGE_CODE)
        except SendMailException:
            logger = logging.getLogger('pretix.presale.user')
            logger.exception('A mail resending order links to {} could not be sent.'.format(user))
            messages.error(self.request, _('We have trouble sending emails right now, please check back later.'))
            return self.get(request, *args, **kwargs)

        messages.success(self.request, _('If there were any orders by this user, they will receive an email with their order codes.'))
        return redirect(eventreverse(self.request.event, 'presale:event.index'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.link_form
        return context


class UnlockHashView(EventViewMixin, View):
    # Allows to register an unlock hash in the user's session, e.g. to unlock a hidden payment provider

    def get(self, request, *args, **kwargs):
        hashes = request.session.get('pretix_unlock_hashes', [])
        hashes.append(kwargs.get('hash'))
        request.session['pretix_unlock_hashes'] = hashes
        return redirect(eventreverse(self.request.event, 'presale:event.index'))
