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
import collections.abc
import warnings

from django.core.paginator import (
    EmptyPage, PageNotAnInteger, UnorderedObjectListWarning,
)
from django.utils.translation import gettext_lazy as _
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


class LargeResultSetPage(collections.abc.Sequence):

    def __init__(self, object_list, number, paginator):
        self.object_list = object_list
        self.number = number
        self.paginator = paginator

    def __repr__(self):
        return '<Page %s>' % self.number

    def __len__(self):
        return len(self.object_list)

    def __getitem__(self, index):
        if not isinstance(index, (slice, int)):
            raise TypeError
        # The object_list is converted to a list so that if it was a QuerySet
        # it won't be a database hit per __getitem__.
        if not isinstance(self.object_list, list):
            self.object_list = list(self.object_list)
        return self.object_list[index]

    def has_next(self):
        try:
            return self[self.paginator.per_page - 1]
        except:
            return False

    def has_previous(self):
        return self.number > 1

    def has_other_pages(self):
        return self.has_previous() or self.has_next()

    def next_page_number(self):
        return self.paginator.validate_number(self.number + 1)

    def previous_page_number(self):
        return self.paginator.validate_number(self.number - 1)

    def start_index(self):
        """
        Returns the 1-based index of the first object on this page,
        relative to total objects in the paginator.
        """
        # Special case, return zero if no items.
        if self.paginator.count == 0:
            return 0
        return (self.paginator.per_page * (self.number - 1)) + 1

    def end_index(self):
        """
        Returns the 1-based index of the last object on this page,
        relative to total objects found (hits).
        """
        # Special case for the last page because there can be orphans.
        if self.number == self.paginator.num_pages:
            return self.paginator.count
        return self.number * self.paginator.per_page


class LargeResultSetPaginator(object):

    def __init__(self, object_list, per_page, orphans=0,
                 allow_empty_first_page=True):
        self.object_list = object_list
        self._check_object_list_is_ordered()
        self.per_page = int(per_page)
        self.orphans = int(orphans)

    def validate_number(self, number):
        """
        Validates the given 1-based page number.
        """
        try:
            number = int(number)
        except (TypeError, ValueError):
            raise PageNotAnInteger(_('That page number is not an integer'))
        if number < 1:
            raise EmptyPage(_('That page number is less than 1'))
        return number

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        return self._get_page(self.object_list[bottom:top], number, self)

    def _get_page(self, *args, **kwargs):
        """
        Returns an instance of a single page.

        This hook can be used by subclasses to use an alternative to the
        standard :cls:`Page` object.
        """
        return LargeResultSetPage(*args, **kwargs)

    def _check_object_list_is_ordered(self):
        """
        Warn if self.object_list is unordered (typically a QuerySet).
        """
        ordered = getattr(self.object_list, 'ordered', None)
        if ordered is not None and not ordered:
            obj_list_repr = (
                '{} {}'.format(self.object_list.model, self.object_list.__class__.__name__)
                if hasattr(self.object_list, 'model')
                else '{!r}'.format(self.object_list)
            )
            warnings.warn(
                'Pagination may yield inconsistent results with an unordered '
                'object_list: {}.'.format(obj_list_repr),
                UnorderedObjectListWarning,
                stacklevel=3
            )
