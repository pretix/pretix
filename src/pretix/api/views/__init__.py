from calendar import timegm

from django.db.models import Max
from django.http import HttpResponse
from django.utils.http import http_date, parse_http_date_safe
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


class ConditionalListView:

    def list(self, request, **kwargs):
        if_modified_since = request.META.get('HTTP_IF_MODIFIED_SINCE')
        if if_modified_since:
            if_modified_since = parse_http_date_safe(if_modified_since)
        if_unmodified_since = request.META.get('HTTP_IF_UNMODIFIED_SINCE')
        if if_unmodified_since:
            if_unmodified_since = parse_http_date_safe(if_unmodified_since)
        if not hasattr(request, 'event'):
            return super().list(request, **kwargs)

        lmd = request.event.logentry_set.filter(
            content_type__model=self.queryset.model._meta.model_name,
            content_type__app_label=self.queryset.model._meta.app_label,
        ).aggregate(
            m=Max('datetime')
        )['m']
        if lmd:
            lmd_ts = timegm(lmd.utctimetuple())

        if if_unmodified_since and lmd and lmd_ts > if_unmodified_since:
            return HttpResponse(status=412)

        if if_modified_since and lmd and lmd_ts <= if_modified_since:
            return HttpResponse(status=304)

        resp = super().list(request, **kwargs)
        if lmd:
            resp['Last-Modified'] = http_date(lmd_ts)
        return resp
