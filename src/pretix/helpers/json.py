from django.core.files import File
from i18nfield.utils import I18nJSONEncoder
from phonenumber_field.phonenumber import PhoneNumber

from pretix.base.reldate import RelativeDateWrapper


class CustomJSONEncoder(I18nJSONEncoder):
    def default(self, obj):
        if isinstance(obj, RelativeDateWrapper):
            return obj.to_string()
        elif isinstance(obj, File):
            return obj.name
        if isinstance(obj, PhoneNumber):
            return str(obj)
        else:
            return super().default(obj)


def safe_string(original):
    return original.replace("<", "\\u003C").replace(">", "\\u003E")
