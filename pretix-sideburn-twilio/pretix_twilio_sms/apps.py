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
        self._patch_mail_send_task()

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

    def _patch_mail_send_task(self):
        from django.apps import apps

        if not apps.is_installed("pretix_twilio_sms"):
            return

        from pretix.base.services import mail as mail_module

        import logging
        from pretix_twilio_sms.services import queue_waiting_list_sms_after_mail

        mail_send_task = mail_module.mail_send_task
        original_run = mail_send_task.run
        _log = logging.getLogger("pretix_twilio_sms.apps")

        def run_with_post_send_sms(*args, **kwargs):
            from celery import current_task
            result = original_run(current_task, *args, **kwargs)
            _log.info(
                "pretix_twilio_sms: mail_send_task finished, checking for waiting list SMS "
                "event_id=%s order=%s customer=%s",
                kwargs.get("event"),
                kwargs.get("order"),
                kwargs.get("customer"),
            )
            queue_waiting_list_sms_after_mail(
                event_id=kwargs.get("event"),
                order=kwargs.get("order"),
                customer=kwargs.get("customer"),
                to=kwargs.get("to"),
            )
            return result

        mail_send_task.run = run_with_post_send_sms
