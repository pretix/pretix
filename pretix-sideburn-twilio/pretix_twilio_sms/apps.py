from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_twilio_sms"
    verbose_name = "Sideburn Twilio Integration"

    class PretixPluginMeta:
        name = gettext_lazy("Sideburn Twilio Integration")
        author = "Ryan"
        description = gettext_lazy("A Sideburn-specific twilio integration for pretix")
        visible = True
        version = __version__
        category = "INTEGRATION"
        compatibility = "pretix>=2.7.0"
        settings_links = []
        navigation_links = []

    def ready(self):
        from . import signals  # NOQA
        self._patch_customer_views()
        self._patch_waitinglist_send_voucher()

    def _patch_customer_views(self):
        from django.apps import apps

        if not apps.is_installed("pretix_twilio_sms"):
            return

        from pretix.presale.views import customer as presale_customer

        def profile_get_template_names(self):
            return ["pretix_twilio_sms/customer_profile.html"]

        from pretix_twilio_sms.forms import ChangeInfoFormWithSms

        presale_customer.ProfileView.get_template_names = profile_get_template_names
        presale_customer.ChangeInformationView.form_class = ChangeInfoFormWithSms

    def _patch_waitinglist_send_voucher(self):
        from django.apps import apps

        if not apps.is_installed("pretix_twilio_sms"):
            return

        from pretix.base.models.waitinglist import WaitingListEntry

        import logging
        from pretix_twilio_sms.services import queue_waiting_list_sms_for_entry

        original_send_voucher = WaitingListEntry.send_voucher
        _log = logging.getLogger("pretix_twilio_sms.apps")

        def send_voucher_with_queued_sms(self, *args, **kwargs):
            result = original_send_voucher(self, *args, **kwargs)
            _log.info(
                "pretix_twilio_sms: waiting list voucher handled, checking for SMS "
                "event_id=%s entry_id=%s",
                getattr(self.event, "id", None),
                self.pk,
            )
            queue_waiting_list_sms_for_entry(entry=self)
            return result

        WaitingListEntry.send_voucher = send_voucher_with_queued_sms
