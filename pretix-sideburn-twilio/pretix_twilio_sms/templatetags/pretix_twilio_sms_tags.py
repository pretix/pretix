from django import template

register = template.Library()


@register.simple_tag
def get_sms_opt_in(customer):
    """
    Return True if the customer has opted into SMS updates, False otherwise.
    Handles missing CustomerSmsPreference (e.g. no record or plugin not installed).
    """
    try:
        from pretix_twilio_sms.models import CustomerSmsPreference
    except ImportError:
        return False

    try:
        return customer.sms_preference.sms_opt_in
    except CustomerSmsPreference.DoesNotExist:
        return False
    except AttributeError:
        return False
