from decimal import Decimal

from django.conf import settings
from django.core.validators import DecimalValidator
from django.forms import NumberInput, TextInput
from django.utils import formats


class DecimalTextInput(TextInput):
    def __init__(self, *args, **kwargs):
        self.places = kwargs.pop('places', 2)
        super().__init__(*args, **kwargs)

    def format_value(self, value):
        """
        Return a value as it should appear when rendered in a template.
        """
        if value == '' or value is None:
            return None
        if isinstance(value, str):
            return value
        if not isinstance(value, Decimal):
            value = Decimal(value)
        return formats.localize_input(value.quantize(Decimal('1') / 10 ** self.places))


def change_decimal_field(field, currency):
    places = settings.CURRENCY_PLACES.get(currency, 2)
    field.decimal_places = places
    field.localize = True
    if isinstance(field.widget, NumberInput):
        field.widget.attrs['step'] = str(Decimal('1') / 10 ** places).lower()
    elif isinstance(field.widget, TextInput):
        field.widget = DecimalTextInput(places=places)
    v = [v for v in field.validators if isinstance(v, DecimalValidator)]
    if len(v) == 1:
        v[0].decimal_places = places
