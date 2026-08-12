from rest_framework import viewsets, serializers
from django.db import transaction
from .styles import AVAILABLE_STYLES_DICT, AVAILABLE_PLATFORMS
from .models import WalletLayout, WalletPlatformLayout
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.fields import UploadedFileField
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

class WalletPlatformLayoutSerializer(I18nAwareModelSerializer):
    platform = serializers.ChoiceField(
        choices=[p.identifier for p in AVAILABLE_PLATFORMS]
    )
    style = serializers.CharField(allow_null=True, required=False)

    class Meta:
        model = WalletPlatformLayout
        fields = ("platform", "style", "layout")

    def validate_layout(self, value):
        if not isinstance(value, dict):
            raise ValidationError(_("Layout must be a dict"))
        return value

    def validate(self, data):
        platform = data.get("platform")
        style = data.get("style")
        layout = data.get("layout")
        if platform and style and layout:
            platform_styles = AVAILABLE_STYLES_DICT[platform]

            if data["style"] not in platform_styles:
                raise ValidationError(_("Invalid style"))
            style = platform_styles[data["style"]]

            style = style(event=self.context["event"], layout=data["layout"])
            style.validate()
            data['file_settings'] = style.extract_file_settings(self.context['request'])

        return data

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['file_settings'] = {}
        for file_setting in instance.file_settings.all():
            try:
                url = file_setting.file.url
            except AttributeError:
                continue
            request = self.context['request']
            ret['file_settings'][file_setting.key] = request.build_absolute_uri(url)
        return ret


class WalletLayoutSerializer(I18nAwareModelSerializer):
    platform_layouts = WalletPlatformLayoutSerializer(many=True)

    class Meta:
        model = WalletLayout
        fields = ("id", "name", "platform_layouts")
        read_only_fields = ("id",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs, event=self.context["event"])

    def update(self, instance, validated_data):
        platform_layouts = validated_data.pop("platform_layouts")
        for layout in platform_layouts:
            if layout["style"]:
                # TODO: better handling here
                file_settings = layout.pop("file_settings", {})
                obj, _ = instance.platform_layouts.update_or_create(
                    platform=layout["platform"], defaults=layout
                )
                for key, file in file_settings.items():
                    if not file:
                        obj.file_settings.filter(key=key).delete()

                    elif file != "keep":
                        obj.file_settings.update_or_create(key=key, defaults={"file": file})

        instance.platform_layouts.exclude(
            platform__in={
                layout["platform"]
                for layout in platform_layouts
                if layout["style"] is not None
            }
        ).delete()
        return super().update(instance, validated_data)


class WalletLayoutViewSet(viewsets.ModelViewSet):
    model = WalletLayout
    queryset = WalletLayout.objects.none()
    serializer_class = WalletLayoutSerializer
    permission = "event.settings.general:write"

    def get_queryset(self):
        return self.request.event.wallet_layouts.all()

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
