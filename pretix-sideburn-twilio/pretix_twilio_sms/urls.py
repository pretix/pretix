"""
URL configuration for the pretix Twilio SMS plugin.
"""
from django.urls import re_path

from .views import TwilioWebhookView

urlpatterns = [
    re_path(
        r"^_twilio_sms/webhook/$",
        TwilioWebhookView.as_view(),
        name="webhook",
    ),
]