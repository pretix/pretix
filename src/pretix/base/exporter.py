import json

from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver
from typing import Tuple

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

    def render(self, form_data: dict) -> Tuple[str, str, str]:
        """
        Render the exported file and return a tuple consisting of a filename, a file type
        and file content.

        :type form_data: dict
        :param form_data: The form data of the export details form
        """
        raise NotImplementedError()  # NOQA


class JSONExporter(BaseExporter):
    identifier = 'json'
    verbose_name = 'JSON'

    def render(self, form_data):
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
                        'id': category.identity,
                        'name': str(category.name)
                    } for category in self.event.categories.current.all()
                ],
                'items': [
                    {
                        'id': item.identity,
                        'name': str(item.name),
                        'category': item.category_id,
                        'price': item.default_price,
                        'admission': item.admission,
                        'active': item.active,
                        'variations': [
                            {
                                'id': variation.identity,
                                'active': variation.active,
                                'price': variation.default_price if variation.default_price is not None else item.default_price,
                                'name': str(variation)
                            } for variation in item.variations.current.all()
                        ]
                    } for item in self.event.items.current.all().prefetch_related('variations')
                ],
                'questions': [
                    {
                        'id': question.identity,
                        'question': str(question.question),
                        'type': question.type
                    } for question in self.event.questions.current.all()
                ],
                'orders': [
                    {
                        'code': order.code,
                        'status': order.status,
                        'user': order.user.email,
                        'datetime': order.datetime,
                        'payment_fee': order.payment_fee,
                        'total': order.total,
                        'positions': [
                            {
                                'id': position.identity,
                                'item': position.item_id,
                                'variation': position.variation_id,
                                'price': position.price,
                                'attendee_name': position.attendee_name,
                                'answers': [
                                    {
                                        'question': answer.question_id,
                                        'answer': answer.answer
                                    } for answer in position.answers.all()
                                ]
                            } for position in order.positions.current.all()
                        ]
                    } for order in
                    self.event.orders.current.all().prefetch_related('positions', 'positions__answers').select_related(
                        'user')
                ],
                'quotas': [
                    {
                        'id': quota.identity,
                        'size': quota.size,
                        'items': [item.id for item in quota.items.all()],
                        'variations': [variation.id for variation in quota.variations.all()],
                    } for quota in self.event.quotas.current.all().prefetch_related('items', 'variations')
                ]
            }
        }

        return 'pretixdata.json', 'application/json', json.dumps(jo, cls=DjangoJSONEncoder)


@receiver(register_data_exporters, dispatch_uid="exporter_json")
def register_json_export(sender, **kwargs):
    return JSONExporter
