import django_filters
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from pretix.api.serializers.item import (
    ItemAddOnSerializer, ItemCategorySerializer, ItemSerializer,
    ItemVariationSerializer, QuestionOptionSerializer, QuestionSerializer,
    QuotaSerializer,
)
from pretix.api.views import ConditionalListView
from pretix.base.models import (
    Item, ItemAddOn, ItemCategory, ItemVariation, Question, QuestionOption,
    Quota,
)
from pretix.helpers.dicts import merge_dicts


class ItemFilter(FilterSet):
    tax_rate = django_filters.CharFilter(method='tax_rate_qs')

    def tax_rate_qs(self, queryset, name, value):
        if value in ("0", "None", "0.00"):
            return queryset.filter(Q(tax_rule__isnull=True) | Q(tax_rule__rate=0))
        else:
            return queryset.filter(tax_rule__rate=value)

    class Meta:
        model = Item
        fields = ['active', 'category', 'admission', 'tax_rate', 'free_price']


class ItemViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    filterset_class = ItemFilter
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        return self.request.event.items.select_related('tax_rule').prefetch_related('variations', 'addons').all()

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
        ctx['has_variations'] = self.request.data.get('has_variations')
        return ctx

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.item.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

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
        self.get_object().cartposition_set.all().delete()
        super().perform_destroy(instance)


class ItemVariationViewSet(viewsets.ModelViewSet):
    serializer_class = ItemVariationSerializer
    queryset = ItemVariation.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter,)
    ordering_fields = ('id', 'position')
    ordering = ('id',)
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        item = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
        return item.variations.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['item'] = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
        return ctx

    def perform_create(self, serializer):
        item = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
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

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.item.log_action(
            'pretix.event.item.variation.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk},
                             {'value': serializer.instance.value})
        )

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


class ItemAddOnViewSet(viewsets.ModelViewSet):
    serializer_class = ItemAddOnSerializer
    queryset = ItemAddOn.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter,)
    ordering_fields = ('id', 'position')
    ordering = ('id',)
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        item = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
        return item.addons.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['item'] = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
        return ctx

    def perform_create(self, serializer):
        item = get_object_or_404(Item, pk=self.kwargs['item'], event=self.request.event)
        category = get_object_or_404(ItemCategory, pk=self.request.data['addon_category'])
        serializer.save(base_item=item, addon_category=category)
        item.log_action(
            'pretix.event.item.addons.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.base_item.log_action(
            'pretix.event.item.addons.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

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
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ItemCategoryFilter
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        return self.request.event.categories.all()

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

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.category.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

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


class QuestionFilter(FilterSet):
    class Meta:
        model = Question
        fields = ['ask_during_checkin', 'required', 'identifier']


class QuestionViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    queryset = Question.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = QuestionFilter
    ordering_fields = ('id', 'position')
    ordering = ('position', 'id')
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        return self.request.event.questions.prefetch_related('options').all()

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

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.question.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

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
    filter_backends = (DjangoFilterBackend, OrderingFilter,)
    ordering_fields = ('id', 'position')
    ordering = ('position',)
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        q = get_object_or_404(Question, pk=self.kwargs['question'], event=self.request.event)
        return q.options.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['question'] = get_object_or_404(Question, pk=self.kwargs['question'], event=self.request.event)
        return ctx

    def perform_create(self, serializer):
        q = get_object_or_404(Question, pk=self.kwargs['question'], event=self.request.event)
        serializer.save(question=q)
        q.log_action(
            'pretix.event.question.option.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.question.log_action(
            'pretix.event.question.option.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'ORDER': serializer.instance.position}, {'id': serializer.instance.pk})
        )

    def perform_destroy(self, instance):
        instance.question.log_action(
            'pretix.event.question.option.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk}
        )
        super().perform_destroy(instance)


class QuotaFilter(FilterSet):
    class Meta:
        model = Quota
        fields = ['subevent']


class QuotaViewSet(ConditionalListView, viewsets.ModelViewSet):
    serializer_class = QuotaSerializer
    queryset = Quota.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter,)
    filterset_class = QuotaFilter
    ordering_fields = ('id', 'size')
    ordering = ('id',)
    permission = None
    write_permission = 'can_change_items'

    def get_queryset(self):
        return self.request.event.quotas.all()

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
        return ctx

    def perform_update(self, serializer):
        current_subevent = serializer.instance.subevent
        serializer.save(event=self.request.event)
        request_subevent = serializer.instance.subevent
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

    @detail_route(methods=['get'])
    def availability(self, request, *args, **kwargs):
        quota = self.get_object()

        avail = quota.availability()

        data = {
            'paid_orders': quota.count_paid_orders(),
            'pending_orders': quota.count_pending_orders(),
            'blocking_vouchers': quota.count_blocking_vouchers(),
            'cart_positions': quota.count_in_cart(),
            'waiting_list': quota.count_waiting_list_pending(),
            'available_number': avail[1],
            'available': avail[0] == Quota.AVAILABILITY_OK,
            'total_size': quota.size,
        }
        return Response(data)
