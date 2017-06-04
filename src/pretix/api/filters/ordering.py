import coreapi
import coreschema
from django.utils.encoding import force_text
from rest_framework.filters import OrderingFilter


class ExplicitOrderingFilter(OrderingFilter):
    ordering_description = 'Which field to use when ordering the results. You can combine multiple fields ' \
                           'by separating them with a comma and you can invert the order by prepending a ' \
                           'minus sign. Valid fields: {fields}'

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name=self.ordering_param,
                required=False,
                location='query',
                schema=coreschema.String(
                    title=force_text(self.ordering_title),
                    description=force_text(self.ordering_description).format(fields=', '.join(
                        v for k, v in self.get_valid_fields(view.queryset, view)
                    ))
                )
            )
        ]
