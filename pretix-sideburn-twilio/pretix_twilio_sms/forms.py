"""
Form extensions for the Twilio SMS plugin.
"""
from collections import OrderedDict

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import PhoneNumberField

from pretix.base.forms.questions import (
    WrappedPhoneNumberPrefixWidget,
    guess_phone_prefix_from_request,
)
from pretix.base.models import Customer
from pretix.presale.forms.customer import ChangeInfoForm
from pretix.presale.forms.waitinglist import WaitingListForm


class ChangeInfoFormWithSms(ChangeInfoForm):
    """
    Extends ChangeInfoForm with an SMS opt-in checkbox under the phone field.
    Prepopulated from CustomerSmsPreference; updates CustomerSmsPreference on save.
    """

    sms_opt_in = forms.BooleanField(
        label=_("I want to receive SMS updates"),
        required=False,
        initial=False,
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        # Prepopulate from customer's SMS preference
        if self.instance:
            try:
                from .models import CustomerSmsPreference
                self.initial["sms_opt_in"] = self.instance.sms_preference.sms_opt_in
            except (CustomerSmsPreference.DoesNotExist, AttributeError, ImportError):
                self.initial["sms_opt_in"] = False
        # Place sms_opt_in right after phone
        keys = list(self.fields.keys())
        new_order = []
        sms_opt_in_inserted = False
        for key in keys:
            if key == "sms_opt_in":
                continue
            new_order.append(key)
            if key == "phone" and not sms_opt_in_inserted:
                new_order.append("sms_opt_in")
                sms_opt_in_inserted = True
        if not sms_opt_in_inserted:
            new_order.append("sms_opt_in")
        self.fields = OrderedDict((k, self.fields[k]) for k in new_order)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if not commit:
            return instance
        from .models import CustomerSmsPreference
        opt_in = self.cleaned_data.get("sms_opt_in", False)
        pref, created = CustomerSmsPreference.objects.get_or_create(
            customer=instance,
            defaults={"sms_opt_in": opt_in},
        )
        if not created and pref.sms_opt_in != opt_in:
            pref.sms_opt_in = opt_in
            pref.save(update_fields=["sms_opt_in", "last_changed"])
        return instance


class WaitingListFormWithSms(WaitingListForm):
    """
    Extends WaitingListForm with SMS opt-in and optional phone field when
    the event does not ask for phone. Updates Customer.phone and
    CustomerSmsPreference on save when applicable.
    """

    sms_opt_in = forms.BooleanField(
        label=_("Send me SMS notifications when my waitlist spot is ready"),
        required=False,
        initial=False,
    )

    def __init__(self, *args, **kwargs):
        self._customer = kwargs.get("customer")
        self._request = kwargs.get("request")
        super().__init__(*args, **kwargs)
        # When event does not ask for phone, add our own phone field for SMS
        if "phone" not in self.fields:
            if not self.initial.get("sms_phone") and self._customer and self._customer.phone:
                self.initial["sms_phone"] = self._customer.phone
            if self._request and self.event:
                phone_prefix = guess_phone_prefix_from_request(self._request, self.event)
                if phone_prefix and not self.initial.get("sms_phone"):
                    self.initial["sms_phone"] = "+{}.".format(phone_prefix)
            self.fields["sms_phone"] = PhoneNumberField(
                label=_("Phone number for SMS"),
                required=False,
                help_text=_("Required if you opt in to SMS notifications."),
                widget=WrappedPhoneNumberPrefixWidget(),
            )
            self.fields["sms_opt_in"].widget.attrs["data-sms-phone-field"] = "sms_phone"
        else:
            # Pre-populate phone from customer when event asks for phone
            if not self.initial.get("phone") and self._customer and self._customer.phone:
                self.initial["phone"] = self._customer.phone

        # Ensure sms_opt_in appears right after phone / sms_phone
        if "sms_opt_in" in self.fields:
            keys = list(self.fields.keys())
            new_order = []
            sms_opt_in_inserted = False
            for key in keys:
                if key == "sms_opt_in":
                    continue
                new_order.append(key)
                if (key == "phone" or key == "sms_phone") and not sms_opt_in_inserted:
                    new_order.append("sms_opt_in")
                    sms_opt_in_inserted = True
            if not sms_opt_in_inserted:
                new_order.append("sms_opt_in")
            self.fields = OrderedDict((k, self.fields[k]) for k in new_order)

    def clean(self):
        data = super().clean()
        sms_opt_in = data.get("sms_opt_in")
        if sms_opt_in:
            phone = data.get("phone") or data.get("sms_phone")
            if not phone:
                field = "sms_phone" if "sms_phone" in self.fields else "phone"
                self.add_error(field, _("A phone number is required when opting in to SMS notifications."))
        return data

    def save(self, commit=True):
        # If we added sms_phone, set instance.phone from it before saving the entry
        if "sms_phone" in self.fields and self.cleaned_data.get("sms_phone"):
            self.instance.phone = self.cleaned_data["sms_phone"]
        instance = super().save(commit=commit)
        if not commit:
            return instance

        email = (instance.email or "").strip().lower()
        if not email:
            return instance

        organizer = instance.event.organizer
        try:
            customer = Customer.objects.get(organizer=organizer, email=email)
        except Customer.DoesNotExist:
            return instance

        # Update customer.phone if empty and we have a phone from the form
        phone_value = instance.phone or self.cleaned_data.get("sms_phone")
        if phone_value and not customer.phone:
            customer.phone = phone_value
            customer.save(update_fields=["phone"])

        # Create or update CustomerSmsPreference when user opted in
        if self.cleaned_data.get("sms_opt_in"):
            from .models import CustomerSmsPreference

            pref, _ = CustomerSmsPreference.objects.get_or_create(
                customer=customer,
                defaults={"sms_opt_in": True},
            )
            if not pref.sms_opt_in:
                pref.sms_opt_in = True
                pref.save(update_fields=["sms_opt_in", "last_changed"])

        return instance
