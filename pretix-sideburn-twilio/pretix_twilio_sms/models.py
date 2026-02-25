from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomerSmsPreference(models.Model):
    """
    Stores per-customer SMS opt-in preference.
    """

    customer = models.OneToOneField(
        "pretixbase.Customer",
        on_delete=models.CASCADE,
        related_name="sms_preference",
        verbose_name=_("Customer"),
    )
    sms_opt_in = models.BooleanField(
        default=False,
        verbose_name=_("SMS opt-in"),
        help_text=_("Whether the customer agreed to receive SMS notifications."),
    )
    last_changed = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Last changed"),
    )

    class Meta:
        verbose_name = _("Customer SMS preference")
        verbose_name_plural = _("Customer SMS preferences")

    def __str__(self):
        return "{} ({})".format(
            self.customer,
            _("opted in") if self.sms_opt_in else _("opted out"),
        )
