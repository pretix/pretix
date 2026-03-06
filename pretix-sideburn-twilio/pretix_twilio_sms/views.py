"""
Views for the pretix Twilio SMS plugin.
"""
import logging

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_scopes import scopes_disabled

from pretix_twilio_sms.models import CustomerSmsPreference

logger = logging.getLogger(__name__)

# Empty TwiML response for Twilio webhook.
TWIML_EMPTY_RESPONSE = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _get_webhook_auth_token():
    """
    Get the auth token used to validate Twilio webhook signatures.
    Twilio signs requests with the Account Auth Token.
    """
    from pretix.base.settings import GlobalSettingsObject

    gs = GlobalSettingsObject()
    return (gs.settings.twilio_auth_token or "").strip()


def _validate_twilio_request(request):
    """
    Validate the incoming request using Twilio's X-Twilio-Signature header.
    Returns True if valid or if validation is skipped (no auth token configured).
    Returns False if validation fails.
    """
    auth_token = _get_webhook_auth_token()
    if not auth_token:
        logger.warning(
            "pretix_twilio_sms: Twilio webhook validation skipped - no auth token"
        )
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        logger.warning("pretix_twilio_sms: Twilio webhook missing X-Twilio-Signature")
        return False

    url = request.build_absolute_uri(request.get_full_path())
    # Twilio recommends HTTPS for validation; some proxies strip it
    if url.startswith("http://"):
        url = "https://" + url[7:]

    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(auth_token)
        # RequestValidator.validate(url, params, signature)
        params = request.POST.copy()
        if validator.validate(url, params, signature):
            return True
    except Exception as e:
        logger.exception(
            "pretix_twilio_sms: Twilio webhook validation error: %s", e
        )
        return False

    logger.warning("pretix_twilio_sms: Twilio webhook signature invalid")
    return False


def _normalize_phone(phone):
    """Normalize phone to the same format Customer.phone uses (for filtering)."""
    if not phone or not phone.strip():
        return None
    try:
        from phonenumber_field.phonenumber import PhoneNumber

        return PhoneNumber.from_string(phone.strip())
    except Exception:
        return None


def _update_sms_preference_for_phone(phone, sms_opt_in):
    """
    Find Customer(s) by phone and update CustomerSmsPreference.
    Phone may match multiple customers across organizers; we update all.
    """
    from pretix.base.models import Customer

    normalized = _normalize_phone(phone)
    if normalized is None:
        return 0

    with scopes_disabled():
        # Search across all organizers (Customer is organizer-scoped)
        customers = list(
            Customer.objects.filter(phone=normalized).select_related("organizer")
        )

        updated = 0
        for customer in customers:
            try:
                pref, created = CustomerSmsPreference.objects.get_or_create(
                    customer=customer,
                    defaults={"sms_opt_in": sms_opt_in},
                )
                if not created and pref.sms_opt_in != sms_opt_in:
                    pref.sms_opt_in = sms_opt_in
                    pref.save()
                    updated += 1
                elif created:
                    updated += 1
            except Exception as e:
                logger.exception(
                    "pretix_twilio_sms: Failed to update CustomerSmsPreference "
                    "customer_id=%s: %s",
                    customer.pk,
                    e,
                )

    return updated


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class TwilioWebhookView(View):
    """
    Handle Twilio incoming SMS webhooks for STOP/START (opt-out/opt-in).

    When a user replies STOP or START to an SMS, Twilio sends a webhook
    with OptOutType set. This view maps the From phone number to
    Customer(s) and updates CustomerSmsPreference accordingly.
    """

    def post(self, request, *args, **kwargs):
        if not _validate_twilio_request(request):
            return HttpResponse(status=403)

        from_phone = (request.POST.get("From") or "").strip()
        opt_out_type = (request.POST.get("OptOutType") or "").strip().upper()

        if not from_phone:
            logger.info(
                "pretix_twilio_sms: Twilio webhook missing From, returning 200"
            )
            return HttpResponse(
                TWIML_EMPTY_RESPONSE,
                content_type="text/xml",
            )

        if opt_out_type == "STOP":
            count = _update_sms_preference_for_phone(from_phone, sms_opt_in=False)
            logger.info(
                "pretix_twilio_sms: Twilio STOP from %s, updated %d preference(s)",
                from_phone,
                count,
            )
        elif opt_out_type == "START":
            count = _update_sms_preference_for_phone(from_phone, sms_opt_in=True)
            logger.info(
                "pretix_twilio_sms: Twilio START from %s, updated %d preference(s)",
                from_phone,
                count,
            )
        else:
            # No OptOutType or unknown value - just return empty response
            logger.debug(
                "pretix_twilio_sms: Twilio webhook From=%s OptOutType=%s (ignored)",
                from_phone,
                opt_out_type or "(empty)",
            )

        return HttpResponse(
            TWIML_EMPTY_RESPONSE,
            content_type="text/xml",
        )