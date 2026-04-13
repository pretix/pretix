from rest_framework import viewsets
from django.db import transaction
from .styles import PassLayout, get_platform_styles, get_platforms
from .models import WalletLayout
from pretix.api.serializers.i18n import I18nAwareModelSerializer
import django_filters.rest_framework
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class WalletLayoutSerializer(I18nAwareModelSerializer):
    class Meta:
        model = WalletLayout
        fields = ("event","platform","name","style","layout")
        read_only_fields = ("event", "platform")

    def validate_layout(self, value):
        if not isinstance(value, dict):
            raise ValidationError(_("Layout must be a dict"))
        return value
    

    def validate_platform(self, value):
        if value not in get_platforms():
            raise ValidationError(_("Invalid Platform"))
        return value

    def validate(self, data):
        if "style" in data and "layout" in data and "platform" in data:
            platform_styles = get_platform_styles(data['platform'])
            if data['style'] not in platform_styles:
                raise ValidationError(_("Invalid style"))
            style = get_platform_styles(data['platform'])[data['style']]

            layout = PassLayout(
                style=style, layout=data["layout"]
            )
            breakpoint()
            layout.validate(data['event'])
        return data



class WalletLayoutViewSet(viewsets.ModelViewSet):
    model = WalletLayout
    queryset = WalletLayout.objects.none()
    serializer_class = WalletLayoutSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_fields = ['platform']
    permission = "event.settings.general:write"

    def get_queryset(self):
        return self.request.event.wallet_layouts.all()
    
    def get_serializer(self, *args, **kwargs):
        return super().get_serializer(*args, **kwargs)
    

    @transaction.atomic()
    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            action='pretix.plugins.wallet.layout.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
