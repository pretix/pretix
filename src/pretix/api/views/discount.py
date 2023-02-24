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
# This file contains Apache-licensed contributions copyrighted by: Ture Gjørup
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from pretix.api.pagination import TotalOrderingFilter
from pretix.api.serializers.discount import DiscountSerializer
from pretix.api.views import ConditionalListView
from pretix.base.models import CartPosition, Discount

with scopes_disabled():
    class DiscountFilter(FilterSet):
        class Meta:
            model = Discount
            fields = ['active']


class DiscountViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = DiscountSerializer
    queryset = Discount.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    filterset_class = DiscountFilter
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        return self.request.event.discounts.all()

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.discount.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.discount.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('You cannot delete this discount because it already has '
                                   'been used as part of an order.')

        instance.log_action(
            'pretix.event.discount.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        CartPosition.objects.filter(discount=instance).update(discount=None)
        super().perform_destroy(instance)
