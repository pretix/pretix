from functools import reduce

from rest_framework import serializers
from rest_framework.exceptions import APIException


class CompatException(APIException):
    status = 410
    default_code = 'incompatible_data'


class MergeField(serializers.Field):
    """
    Read-only field that iterates over a list of related objects, picks a value from each, and merges the values
    in a configurable way (mode parameter).

    :param mode: list:       returns a list of all picked values
                 consensus:  returns the value only if it is equal on all related objects, otherwise
                             raises or returns an error object
                 union:      only supported if picked values are iterables - generates union of all sub-items
                 bool_or:    returns a boolean that is true if at least one picked value is truthy
    """
    def __init__(self, related_name, inner_field, mode, **kwargs):
        self.inner_field = inner_field
        self.related_name = related_name
        self.merge_mode = mode
        assert mode in ('list', 'consensus', 'union', 'bool_or',)
        kwargs['source'] = '*'
        kwargs['read_only'] = True
        super().__init__(**kwargs)

    def bind(self, field_name, parent):
        self.field_name = field_name
        self.parent = parent
        self.inner_field.bind(field_name, parent)

    def get_attribute(self, instance):
        vals = []
        for ref in getattr(instance, self.related_name).all():
            val = self.inner_field.get_attribute(ref)
            if val is not None:
                val = self.inner_field.to_representation(val)
            vals.append(val)
        if self.merge_mode == 'list':
            return vals
        elif self.merge_mode == 'consensus':
            if len(vals) >= 1 and all(val == vals[0] for val in vals):
                return vals[0]
            else:
                errmes = 'Questionnaire configuration incompatible with old data model due to conflicting values of ' + self.field_name
                if self.context['ignore_errors']:
                    return {'_error': errmes, '_values': vals}
                else:
                    raise CompatException({'detail': errmes, '_values': vals})
        elif self.merge_mode == 'union':
            return list(set(sum(vals, [])))
        elif self.merge_mode == 'bool_or':
            return reduce(lambda a, b: a or bool(b), vals, False)
        else:
            raise Exception('Unknown merge mode: ' + self.merge_mode)

    def to_representation(self, value):
        return value
