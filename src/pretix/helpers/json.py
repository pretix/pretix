from django.core.files import File
from i18nfield.utils import I18nJSONEncoder

from pretix.base.reldate import RelativeDateWrapper


class CustomJSONEncoder(I18nJSONEncoder):
    def default(self, obj):
        if isinstance(obj, RelativeDateWrapper):
            return obj.to_string()
        elif isinstance(obj, File):
            return obj.name
        else:
            return super().default(obj)


def safe_string(original):
    return original.replace("<", "\\u003C").replace(">", "\\u003E")
