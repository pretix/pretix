import logging
from string import Formatter

logger = logging.getLogger(__name__)


class SafeFormatter(Formatter):
    """
    Customized version of ``str.format`` that (a) behaves just like ``str.format_map`` and
    (b) does not allow any unwanted shenanigans like attribute access or format specifiers.
    """
    def __init__(self, context):
        self.context = context

    def get_field(self, field_name, args, kwargs):
        if '.' in field_name or '[' in field_name:
            logger.warning(f'Ignored invalid field name "{field_name}"')
            return ('{' + str(field_name) + '}', field_name)
        return super().get_field(field_name, args, kwargs)

    def get_value(self, key, args, kwargs):
        if key not in self.context:
            return '{' + str(key) + '}'
        return self.context[key]

    def format_field(self, value, format_spec):
        # Ignore format _spec
        return super().format_field(value, '')


def format_map(template, context):
    if not isinstance(template, str):
        template = str(template)
    return SafeFormatter(context).format(template)
