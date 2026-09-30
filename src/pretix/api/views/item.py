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

import django_filters
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from pretix.api.pagination import TotalOrderingFilter
from pretix.api.serializers.item import (
    CompatQuestionSerializer, ItemAddOnSerializer, ItemBundleSerializer, ItemCategorySerializer,
    ItemProgramTimeSerializer, ItemSerializer, ItemVariationSerializer,
    QuestionnaireSerializer, QuestionOptionSerializer, DatafieldSerializer,
    QuotaSerializer, cook_id_from_parts, uncook_id,
)
from pretix.api.views import ConditionalListView
from pretix.base.forms.questions import REQUIRED_NAME_PARTS
from pretix.base.models import (
    CartPosition, Item, ItemAddOn, ItemBundle, ItemCategory, ItemProgramTime,
    ItemVariation, Question, QuestionOption, Quota,
)
from pretix.base.models.items import Questionnaire, QuestionnaireChild
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.settings import PERSON_NAME_SALUTATIONS, PERSON_NAME_SCHEMES, PERSON_NAME_TITLE_GROUPS
from pretix.control.views.item import i18n_all_from_gettext
from pretix.helpers.dicts import merge_dicts
from pretix.helpers.i18n import i18ncomp

with scopes_disabled():
    class ItemFilter(FilterSet):
        tax_rate = django_filters.CharFilter(method='tax_rate_qs')
        search = django_filters.CharFilter(method='search_qs')

        def search_qs(self, queryset, name, value):
            return queryset.filter(
                Q(internal_name__icontains=value) | Q(name__icontains=i18ncomp(value))
            )

        def tax_rate_qs(self, queryset, name, value):
            if value in ("0", "None", "0.00"):
                return queryset.filter(Q(tax_rule__isnull=True) | Q(tax_rule__rate=0))
            else:
                return queryset.filter(tax_rule__rate=value)

        class Meta:
            model = Item
            fields = ['active', 'category', 'admission', 'tax_rate', 'free_price']

    class ItemVariationFilter(FilterSet):
        search = django_filters.CharFilter(method='search_qs')

        def search_qs(self, queryset, name, value):
            return queryset.filter(
                Q(value__icontains=i18ncomp(value))
            )

        class Meta:
            model = ItemVariation
            fields = ['active']


class ItemViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    filterset_class = ItemFilter
    permission = None
    write_permission = 'event.items:write'

    def get_queryset(self):
        return self.request.event.items.select_related('tax_rule').prefetch_related(
            'variations', 'addons', 'bundles', 'meta_values', 'meta_values__property',
            'variations__meta_values', 'variations__meta_values__property',
            'require_membership_types', 'variations__require_membership_types',
            'limit_sales_channels', 'variations__limit_sales_channels', 'program_times'
        ).all()

    @transaction.atomic()
    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.item.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_update(self, serializer):
        original_data = self.get_serializer(instance=serializer.instance).data

        serializer.save(event=self.request.event)

        if serializer.data == original_data:
            # Performance optimization: If nothing was changed, we do not need to save or log anything.
            # This costs us a few cycles on save, but avoids thousands of lines in our log.
            return
        serializer.instance.log_action(
            'pretix.event.item.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('This item cannot be deleted because it has already been ordered '
                                   'by a user or currently is in a users\'s cart. Please set the item as '
                                   '"inactive" instead.')

        instance.log_action(
            'pretix.event.item.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        CartPosition.objects.filter(addon_to__item=instance).delete()
        instance.cartposition_set.all().delete()
        super().perform_destroy(instance)


class ItemVariationViewSet(viewsets.ModelViewSet):
    serializer_class = ItemVariationSerializer
    queryset = ItemVariation.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter,)
    filterset_class = ItemVariationFilter
    ordering_fields = ('id', 'position')
    ordering = ('id',)
    permission = None
    write_permission = 'event.items:write'

    @cached_property
    def item(self):
        return get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)

    def get_queryset(self):
        return self.item.variations.all().prefetch_related(
            'meta_values',
            'meta_values__property',
            'require_membership_types',
            'limit_sales_channels',
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['item'] = self.item
        ctx['event'] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        item = self.item
        if not item.has_variations:
            raise PermissionDenied('This variation cannot be created because the item does not have variations. '
                                   'Changing a product without variations to a product with variations is not allowed.')
        serializer.save(item=item)
        item.log_action(
            'pretix.event.item.variation.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk},
                             {'value': serializer.instance.value})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.item.log_action(
            'pretix.event.item.variation.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk},
                             {'value': serializer.instance.value})
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('This variation cannot be deleted because it has already been ordered '
                                   'by a user or currently is in a users\'s cart. Please set the variation as '
                                   '\'inactive\' instead.')
        if instance.is_only_variation():
            raise PermissionDenied('This variation cannot be deleted because it is the only variation. Changing a '
                                   'product with variations to a product without variations is not allowed.')
        super().perform_destroy(instance)
        instance.item.log_action(
            'pretix.event.item.variation.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data={
                'value': instance.value,
                'id': self.kwargs['pk']
            }
        )


class ItemBundleViewSet(viewsets.ModelViewSet):
    serializer_class = ItemBundleSerializer
    queryset = ItemBundle.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter,)
    ordering_fields = ('id',)
    ordering = ('id',)
    permission = None
    write_permission = 'event.items:write'

    @cached_property
    def item(self):
        return get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)

    def get_queryset(self):
        return self.item.bundles.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['item'] = self.item
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        item = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
        serializer.save(base_item=item)
        item.log_action(
            'pretix.event.item.bundles.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.base_item.log_action(
            'pretix.event.item.bundles.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        instance.base_item.log_action(
            'pretix.event.item.bundles.removed',
            user=self.request.user,
            auth=self.request.auth,
            data={'bundled_item': instance.bundled_item.pk, 'bundled_variation': instance.bundled_variation.pk if instance.bundled_variation else None,
                  'count': instance.count, 'designated_price': instance.designated_price}
        )


class ItemProgramTimeViewSet(viewsets.ModelViewSet):
    serializer_class = ItemProgramTimeSerializer
    queryset = ItemProgramTime.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter,)
    ordering_fields = ('id',)
    ordering = ('id',)
    permission = None
    write_permission = 'event.items:write'

    @cached_property
    def item(self):
        return get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)

    def get_queryset(self):
        if self.request.event.has_subevents:
            raise ValidationError('You cannot use program times on an event series.')
        return self.item.program_times.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['item'] = self.item
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        item = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
        serializer.save(item=item)
        item.log_action(
            'pretix.event.item.program_times.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.item.log_action(
            'pretix.event.item.program_times.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        instance.item.log_action(
            'pretix.event.item.program_times.removed',
            user=self.request.user,
            auth=self.request.auth,
            data={'start': instance.start, 'end': instance.end}
        )


class ItemAddOnViewSet(viewsets.ModelViewSet):
    serializer_class = ItemAddOnSerializer
    queryset = ItemAddOn.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter,)
    ordering_fields = ('id', 'position')
    ordering = ('id',)
    permission = None
    write_permission = 'event.items:write'

    @cached_property
    def item(self):
        return get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)

    def get_queryset(self):
        return self.item.addons.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['item'] = self.item
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        item = self.item
        category = get_object_or_404(ItemCategory, pk=self.request.data['addon_category'])
        serializer.save(base_item=item, addon_category=category)
        item.log_action(
            'pretix.event.item.addons.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.base_item.log_action(
            'pretix.event.item.addons.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        instance.base_item.log_action(
            'pretix.event.item.addons.removed',
            user=self.request.user,
            auth=self.request.auth,
            data={'category': instance.addon_category.pk}
        )


class ItemCategoryFilter(FilterSet):
    class Meta:
        model = ItemCategory
        fields = ['is_addon']


class ItemCategoryViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = ItemCategorySerializer
    queryset = ItemCategory.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    filterset_class = ItemCategoryFilter
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    permission = None
    write_permission = 'event.items:write'

    def get_queryset(self):
        return self.request.event.categories.all()

    @transaction.atomic()
    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.category.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.category.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        for item in instance.items.all():
            item.category = None
            item.save()
        instance.log_action(
            'pretix.event.category.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        super().perform_destroy(instance)


with scopes_disabled():
    class CompatQuestionFilter(FilterSet):
        identifier = django_filters.CharFilter(field_name='question__identifier')
        ask_during_checkin = django_filters.BooleanFilter(method='ask_during_checkin_qs')

        class Meta:
            model = QuestionnaireChild
            fields = ['required']

        def ask_during_checkin_qs(self, qs, name, value):
            return qs.filter(
                questionnaire__type=Questionnaire.QuestionnaireType.ORDER_POSITION_CHECKIN if value else Questionnaire.QuestionnaireType.ORDER_POSITION_SALE
            )


class CompatQuestionViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = CompatQuestionSerializer
    queryset = QuestionnaireChild.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    filterset_class = CompatQuestionFilter
    ordering_fields = ('questionnaire__position', 'position', 'id')
    ordering = ('questionnaire__position', 'position', 'id')
    permission = None
    write_permission = 'event.items:write'

    def get_queryset(self):
        self.sales_channel_ident = self.request.query_params.get('sales_channel', getattr(self.request.auth, 'guessed_sales_channel_identifier', None) or 'web')
        return QuestionnaireChild.objects.filter(
            Q(questionnaire__all_sales_channels=True) | Q(questionnaire__limit_sales_channels__identifier=self.sales_channel_ident),
            questionnaire__event=self.request.event,
            # legacy compat only for position-level questions
            questionnaire__type__startswith='P',
        ).prefetch_related('user_datafield', 'user_datafield__options', 'questionnaire').all()

    def list(self, request, **kwargs):
        resp = super().list(request, **kwargs)
        mangled_results = []
        pos_offset = 0
        for row in resp.data['results']:
            row['position'] += pos_offset
            if row['identifier'] == '@attendee_name_parts':
                settings = self.request.event.settings
                for k, v, w, *__ in PERSON_NAME_SCHEMES.get(settings.name_scheme)['fields']:
                    part = dict(row)
                    part["identifier"] += ":" + k
                    part["question"] = i18n_all_from_gettext(v, settings.locales)
                    if k == "title" and settings.name_scheme_titles:
                        part["type"] = Question.FieldType.CHOICE
                        part["options"] = [{"id": idx + 1, "identifier": k, "answer": i18n_all_from_gettext(k, settings.locales), "position": idx + 1} for idx, k in
                                           enumerate(PERSON_NAME_TITLE_GROUPS.get(settings.name_scheme_titles)[1])]
                    elif k == "salutation":
                        part["type"] = Question.FieldType.CHOICE
                        part["options"] = [{"id": idx + 1, "identifier": k, "answer": i18n_all_from_gettext(v, settings.locales), "position": idx + 1} for idx, (k, v) in
                                           enumerate(PERSON_NAME_SALUTATIONS)]
                    part["id"] = cook_id_from_parts(row['questionnaire_id'], None, part["identifier"][1:])
                    part["required"] = part["required"] and k in REQUIRED_NAME_PARTS
                    mangled_results.append(part)
                    pos_offset += 1
                    row["position"] += 1
            else:
                if row['identifier'] == '@country':
                    row['type'] = Question.FieldType.COUNTRYCODE
                mangled_results.append(row)
        resp.data['results'] = mangled_results
        return resp

    def get_object(self):
        """
        Returns the object the view is displaying.

        You may want to override this if you need to provide non-standard
        queryset lookups.  Eg if objects are referenced using multiple
        keyword arguments in the url conf.
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Perform the lookup filtering.
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        assert lookup_url_kwarg in self.kwargs, (
            'Expected view %s to be called with a URL keyword argument '
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            'attribute on the view correctly.' %
            (self.__class__.__name__, lookup_url_kwarg)
        )

        qid, dfid, sys_df = uncook_id(self.kwargs[lookup_url_kwarg])
        if qid and sys_df:
            obj = get_object_or_404(queryset, questionnaire__pk=qid, system_datafield=sys_df)
        elif qid and dfid:
            obj = get_object_or_404(queryset, questionnaire__pk=qid, user_datafield__pk=dfid)
        else:
            obj = get_object_or_404(queryset, user_datafield__pk=dfid)

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj

    @transaction.atomic()
    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.question.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.question.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.question.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        super().perform_destroy(instance)


with scopes_disabled():
    class DatafieldFilter(FilterSet):
        class Meta:
            model = Question
            fields = ['identifier']


class DatafieldViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = DatafieldSerializer
    queryset = Question.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    filterset_class = DatafieldFilter
    ordering_fields = ('id')
    ordering = ('id')
    permission = None
    write_permission = 'event.items:write'

    def get_queryset(self):
        return self.request.event.questions.filter(
            # the container_type parameter is undocumented, this API is going to change in a later release
            container_type=self.request.GET.get('container_type', Question.ContainerType.ORDERPOSITION),
        ).prefetch_related('options').all()

    @transaction.atomic()
    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.question.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.question.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.question.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        super().perform_destroy(instance)


class QuestionOptionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionOptionSerializer
    queryset = QuestionOption.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter,)
    ordering_fields = ('id', 'position')
    ordering = ('position',)
    permission = None
    write_permission = 'event.items:write'

    def get_queryset(self):
        q = get_object_or_404(Question, pk=self.kwargs['question'], event=self.request.event)
        return q.options.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['question'] = get_object_or_404(Question, pk=self.kwargs['question'], event=self.request.event)
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        q = get_object_or_404(Question, pk=self.kwargs['question'], event=self.request.event)
        serializer.save(question=q)
        q.log_action(
            'pretix.event.question.option.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.question.log_action(
            'pretix.event.question.option.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.question.log_action(
            'pretix.event.question.option.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk}
        )
        super().perform_destroy(instance)


with scopes_disabled():
    class QuestionnaireFilter(FilterSet):
        sales_channel = django_filters.CharFilter(method='sales_channel_qs')

        class Meta:
            model = Questionnaire
            fields = ['type', 'items', 'sales_channel']

        def sales_channel_qs(self, qs, name, value):
            return qs.filter(
                Q(all_sales_channels=True) | Q(limit_sales_channels__identifier=value)
            )


class QuestionnaireViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = QuestionnaireSerializer
    queryset = Questionnaire.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    filterset_class = QuestionnaireFilter
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    permission = None
    write_permission = 'event.items:write'

    def get_queryset(self):
        return self.request.event.questionnaires.prefetch_related('children').all()

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.questionnaire.added',
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
            'pretix.event.questionnaire.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.questionnaire.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        super().perform_destroy(instance)


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass


with scopes_disabled():
    class QuotaFilter(FilterSet):
        items__in = NumberInFilter(
            field_name='items__id',
            lookup_expr='in',
        )

        class Meta:
            model = Quota
            fields = {
                'subevent': ['exact', 'in'],
            }


class QuotaViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = QuotaSerializer
    queryset = Quota.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter,)
    filterset_class = QuotaFilter
    ordering_fields = ('id', 'size')
    ordering = ('id',)
    permission = None
    write_permission = 'event.items:write'

    def get_queryset(self):
        return self.request.event.quotas.select_related('subevent').prefetch_related('items', 'variations').all()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()).distinct()

        page = self.paginate_queryset(queryset)

        if self.request.GET.get('with_availability') == 'true':
            if page:
                qa = QuotaAvailability()
                qa.queue(*page)
                qa.compute(allow_cache=False)
                for q in page:
                    q.available = qa.results[q][0] == Quota.AVAILABILITY_OK
                    q.available_number = qa.results[q][1]

        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @transaction.atomic()
    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.quota.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )
        if serializer.instance.subevent:
            serializer.instance.subevent.log_action(
                'pretix.subevent.quota.added',
                user=self.request.user,
                auth=self.request.auth,
                data=self.request.data
            )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['request'] = self.request
        return ctx

    @transaction.atomic()
    def perform_update(self, serializer):
        original_data = self.get_serializer(instance=serializer.instance).data

        current_subevent = serializer.instance.subevent
        serializer.save(event=self.request.event)
        request_subevent = serializer.instance.subevent

        if serializer.data == original_data:
            # Performance optimization: If nothing was changed, we do not need to save or log anything.
            # This costs us a few cycles on save, but avoids thousands of lines in our log.
            return

        if original_data['closed'] is True and serializer.instance.closed is False:
            serializer.instance.log_action(
                'pretix.event.quota.opened',
                user=self.request.user,
                auth=self.request.auth,
            )
        elif original_data['closed'] is False and serializer.instance.closed is True:
            serializer.instance.log_action(
                'pretix.event.quota.closed',
                user=self.request.user,
                auth=self.request.auth,
            )

        serializer.instance.log_action(
            'pretix.event.quota.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )
        if current_subevent == request_subevent:
            if current_subevent is not None:
                current_subevent.log_action(
                    'pretix.subevent.quota.changed',
                    user=self.request.user,
                    auth=self.request.auth,
                    data=self.request.data
                )
        else:
            if request_subevent is not None:
                request_subevent.log_action(
                    'pretix.subevent.quota.added',
                    user=self.request.user,
                    auth=self.request.auth,
                    data=self.request.data
                )
            if current_subevent is not None:
                current_subevent.log_action(
                    'pretix.subevent.quota.deleted',
                    user=self.request.user,
                    auth=self.request.auth,
                )
        serializer.instance.rebuild_cache()

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.quota.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        if instance.subevent:
            instance.subevent.log_action(
                'pretix.subevent.quota.deleted',
                user=self.request.user,
                auth=self.request.auth,
            )
        super().perform_destroy(instance)

    @action(detail=True, methods=['get'])
    def availability(self, request, *args, **kwargs):
        quota = self.get_object()

        qa = QuotaAvailability(full_results=True)
        qa.queue(quota)
        qa.compute()
        avail = qa.results[quota]

        data = {
            'paid_orders': qa.count_paid_orders[quota],
            'pending_orders': qa.count_pending_orders[quota],
            'exited_orders': qa.count_exited_orders[quota],
            'blocking_vouchers': qa.count_vouchers[quota],
            'cart_positions': qa.count_cart[quota],
            'waiting_list': qa.count_pending_orders[quota],
            'available_number': avail[1],
            'available': avail[0] == Quota.AVAILABILITY_OK,
            'total_size': quota.size,
        }
        return Response(data)
