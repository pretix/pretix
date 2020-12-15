from django import template
from phonenumber_field.phonenumber import PhoneNumber
from phonenumbers import NumberParseException

register = template.Library()


@register.filter("phone_format")
def phone_format(value: str):
    if not value:
        return ""

    if isinstance(value, PhoneNumber) and value.as_international:
        return value.as_international

    try:
        return PhoneNumber.from_string(value).as_international
    except NumberParseException:
        return value
