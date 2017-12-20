from rest_framework.filters import OrderingFilter


class RichOrderingFilter(OrderingFilter):

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)

        if ordering:
            if hasattr(view, 'ordering_custom'):
                newo = []
                for ordering_part in ordering:
                    ob = view.ordering_custom.get(ordering_part)
                    if ob:
                        ob = dict(ob)
                        newo.append(ob.pop('_order'))
                        queryset = queryset.annotate(**ob)
                    else:
                        newo.append(ordering_part)
                ordering = newo
            return queryset.order_by(*ordering)

        return queryset
