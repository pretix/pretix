from rest_framework import viewsets

from pretix.api.models import WebHook
from pretix.api.serializers.webhooks import WebHookSerializer
from pretix.helpers.dicts import merge_dicts


class WebHookViewSet(viewsets.ModelViewSet):
    serializer_class = WebHookSerializer
    queryset = WebHook.objects.none()
    permission = 'can_change_organizer_settings'
    write_permission = 'can_change_organizer_settings'

    def get_queryset(self):
        return self.request.organizer.webhooks.prefetch_related('listeners')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.webhook.created',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    def perform_update(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.webhook.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )
        return inst

    def perform_destroy(self, instance):
        self.request.organizer.log_action(
            'pretix.webhook.changed',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk, 'enabled': False}
        )
        instance.enabled = False
        instance.save(update_fields=['enabled'])
