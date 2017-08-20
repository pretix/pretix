from django.utils import six
from django.utils.encoding import force_text
from django.utils.functional import keep_lazy
from django.utils.safestring import SafeText, mark_safe

_json_escapes = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
}


@keep_lazy(six.text_type, SafeText)
def escapejson(value):
    """Hex encodes characters for use in a application/json type script."""
    return mark_safe(force_text(value).translate(_json_escapes))
