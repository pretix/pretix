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
import datetime
import sys

from django.forms import Form
from django.views.generic.detail import (
    BaseDetailView, SingleObjectTemplateResponseMixin,
)
from django.views.generic.edit import DeletionMixin, FormMixin


def date_fromisocalendar(isoyear, isoweek, isoday):
    if sys.version_info < (3, 8):
        return datetime.datetime.strptime(f'{isoyear}-W{isoweek}-{isoday}', "%G-W%V-%u")
    else:
        return datetime.datetime.fromisocalendar(isoyear, isoweek, isoday)


class CompatDeleteView(SingleObjectTemplateResponseMixin, DeletionMixin, FormMixin, BaseDetailView):
    """
    This is a DeleteView variant that allows us to create subclasses that work on both Django 3.2 and
    Django 4.0.
    """
    form_class = Form
    template_name_suffix = "_confirm_delete"

    def post(self, request, *args, **kwargs):
        # Set self.object before the usual form processing flow.
        # Inlined because having DeletionMixin as the first base, for
        # get_success_url(), makes leveraging super() with ProcessFormView
        # overly complex.
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        return self.delete(self.request, self.args, self.kwargs)
