from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse, JsonResponse

from pretix.base.signals import register_data_exporters


class BaseExporter:
    """
    This is the base class for all data exporters
    """

    def __init__(self, event):
        self.event = event

    def __str__(self):
        return self.identifier

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this exporter. This should be short but
        self-explaining. Good examples include 'JSON' or 'Microsoft Excel'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this exporter.
        This should only contain lowercase letters and in most
        cases will be the same as your packagename.
        """
        raise NotImplementedError()  # NOQA

    @property
    def export_form_fields(self) -> dict:
        """
        When the event's administrator administrator visits the export page, this method
        is called to return the configuration fields available.

        It should therefore return a dictionary where the keys should be field names and
        the values should be corresponding Django form fields.

        We suggest that you return an ``OrderedDict`` object instead of a dictionary.
        Your implementation could look like this::

            @property
            def export_form_fields(self):
                return OrderedDict(
                    [
                        ('tab_width',
                         forms.IntegerField(
                             label=_('Tab width'),
                             default=4
                         ))
                    ]
                )
        """
        return {}

    def render(self, request: HttpRequest) -> HttpResponse:
        """
        Render the exported file and return a request that either contains the file
        or redirects to it.

        :type request: HttpRequest
        :param request: The HTTP request of the user requesting the export
        """
        raise NotImplementedError()  # NOQA


class JSONExporter(BaseExporter):
    identifier = 'json'
    verbose_name = 'JSON'

    def render(self, request):
        jo = {
            'event': {
                'name': str(self.event.name),
                'slug': self.event.slug,
                'organizer': {
                    'name': str(self.event.organizer.name),
                    'slug': self.event.organizer.slug
                },
                'categories': [
                    {
                        'id': c.identity,
                        'name': str(c.name)
                    } for c in self.event.categories.current.all()
                ],
                'items': [
                    {
                        'id': i.identity,
                        'name': str(i.name),
                        'category': i.category_id,
                        'price': i.default_price,
                        'admission': i.admission,
                        'active': i.active,
                        'variations': [
                            {
                                'id': v.identity,
                                'active': v.active,
                                'price': v.default_price if v.default_price is not None else i.default_price,
                                'name': str(v)
                            } for v in i.variations.current.all()
                        ]
                    } for i in self.event.items.current.all().prefetch_related('variations')
                ],
                'questions': [
                    {
                        'id': q.identity,
                        'question': str(q.question),
                        'type': q.type
                    } for q in self.event.questions.current.all()
                ],
                'orders': [
                    {
                        'code': o.code,
                        'status': o.status,
                        'user': o.user.identifier,
                        'datetime': o.datetime,
                        'payment_fee': o.payment_fee,
                        'total': o.total,
                        'positions': [
                            {
                                'item': p.item_id,
                                'variation': p.variation_id,
                                'price': p.price,
                                'attendee_name': p.attendee_name,
                                'answers': [
                                    {
                                        'question': a.question_id,
                                        'answer': a.answer
                                    } for a in p.answers.all()
                                ]
                            } for p in o.positions.current.all()
                        ]
                    } for o in
                    self.event.orders.current.all().prefetch_related('positions', 'positions__answers').select_related(
                        'user')
                ],
                'quotas': [
                    {
                        'id': q.identity,
                        'size': q.size,
                        'items': [i.id for i in q.items.all()],
                        'variations': [v.id for v in q.variations.all()],
                    } for q in self.event.quotas.current.all().prefetch_related('items', 'variations')
                ]
            }
        }

        return JsonResponse(jo)


@receiver(register_data_exporters)
def register_json_export(sender, **kwargs):
    return JSONExporter
