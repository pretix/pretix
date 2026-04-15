from rest_framework import viewsets
from django.db import transaction
from .styles import PassLayout, AVAILABLE_STYLES_DICT
from .models import WalletLayout
from pretix.api.serializers.i18n import I18nAwareModelSerializer
import django_filters.rest_framework
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .views import get_layout_variables


class WalletLayoutSerializer(I18nAwareModelSerializer):
    class Meta:
        model = WalletLayout
        fields = ("id", "platform", "name", "style", "layout")
        read_only_fields = ("id",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['platform'].read_only = True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs, event=self.context["event"])

    def validate_platform(self, value):
        if self.instance and value != self.instance.platform:
            raise ValidationError(_("Platform cannot be changed"))

        if value not in AVAILABLE_STYLES_DICT:
            raise ValidationError(_("Invalid platform"))
        return value

    def validate_layout(self, value):
        if not isinstance(value, dict):
            raise ValidationError(_("Layout must be a dict"))
        return value

    def validate(self, data):
        if self.instance:
            platform = self.instance.platform
        else:
            platform = data.get('platform', None)
        if "style" in data and "layout" in data and platform:
            platform_styles = AVAILABLE_STYLES_DICT[platform]

            if data["style"] not in platform_styles:
                raise ValidationError(_("Invalid style"))
            style = platform_styles[data["style"]]

            layout = PassLayout(style=style, layout=data["layout"])
            context = {"placeholders": {k: {"content": v['content']} for k,v in get_layout_variables(self.context['event']).items()}}
            layout.validate(context=context)
        return data


class WalletLayoutViewSet(viewsets.ModelViewSet):
    model = WalletLayout
    queryset = WalletLayout.objects.none()
    serializer_class = WalletLayoutSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_fields = ["platform"]
    permission = "event.settings.general:write"

    def get_queryset(self):
        return self.request.event.wallet_layouts.all()

    def get_serializer(self, *args, **kwargs):
        return super().get_serializer(*args, **kwargs)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["event"] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            action="pretix.plugins.wallet.layout.changed",
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
