from django.utils.encoding import force_str
from django.utils.functional import keep_lazy
from django.utils.safestring import SafeText, mark_safe

_json_escapes = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
}

_json_escapes_attr = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
    ord('"'): '&#34;',
    ord("'"): '&#39;',
    ord("="): '&#61;',
}


@keep_lazy(str, SafeText)
def escapejson(value):
    """Hex encodes characters for use in a application/json type script."""
    return mark_safe(force_str(value).translate(_json_escapes))


@keep_lazy(str, SafeText)
def escapejson_attr(value):
    """Hex encodes characters for use in a html attributw script."""
    return mark_safe(force_str(value).translate(_json_escapes_attr))
