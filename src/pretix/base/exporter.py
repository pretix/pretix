import json
from collections import OrderedDict

from django import forms
from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver
from django.utils.translation import ugettext as _
from typing import Tuple

from pretix.base.models import Order
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
        When the event's administrator visits the export page, this method
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

        Note: If you use a ``ModelChoiceField`` (or a ``ModelMultipleChoiceField``), the
        ``form_data`` will not contain the model instance but only it's primary key (or
        a list of primary keys) for reasons of internal serialization when using background
        tasks.
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
                        'id': category.id,
                        'name': str(category.name)
                    } for category in self.event.categories.all()
                ],
                'items': [
                    {
                        'id': item.id,
                        'name': str(item.name),
                        'category': item.category_id,
                        'price': item.default_price,
                        'admission': item.admission,
                        'active': item.active,
                        'variations': [
                            {
                                'id': variation.id,
                                'active': variation.active,
                                'price': variation.default_price if variation.default_price is not None else item.default_price,
                                'name': str(variation)
                            } for variation in item.variations.all()
                        ]
                    } for item in self.event.items.all().prefetch_related('variations')
                ],
                'questions': [
                    {
                        'id': question.id,
                        'question': str(question.question),
                        'type': question.type
                    } for question in self.event.questions.all()
                ],
                'orders': [
                    {
                        'code': order.code,
                        'status': order.status,
                        'user': order.email,
                        'datetime': order.datetime,
                        'payment_fee': order.payment_fee,
                        'total': order.total,
                        'positions': [
                            {
                                'id': position.id,
                                'item': position.item_id,
                                'variation': position.variation_id,
                                'price': position.price,
                                'attendee_name': position.attendee_name,
                                'secret': position.secret,
                                'answers': [
                                    {
                                        'question': answer.question_id,
                                        'answer': answer.answer
                                    } for answer in position.answers.all()
                                ]
                            } for position in order.positions.all()
                        ]
                    } for order in
                    self.event.orders.all().prefetch_related('positions', 'positions__answers')
                ],
                'quotas': [
                    {
                        'id': quota.id,
                        'size': quota.size,
                        'items': [item.id for item in quota.items.all()],
                        'variations': [variation.id for variation in quota.variations.all()],
                    } for quota in self.event.quotas.all().prefetch_related('items', 'variations')
                ]
            }
        }

        return 'pretixdata.json', 'application/json', json.dumps(jo, cls=DjangoJSONEncoder)


class MailExporter(BaseExporter):
    identifier = 'mailaddrs'
    verbose_name = _('Email addresses (text file)')

    def render(self, form_data: dict):
        qs = self.event.orders.filter(status__in=form_data['status'])
        addrs = qs.values('email')
        data = "\r\n".join(set(a['email'] for a in addrs))
        return 'pretixemails.txt', 'text/plain', data.encode("utf-8")

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('status',
                 forms.MultipleChoiceField(
                     label=_('Filter by status'),
                     initial=[Order.STATUS_PENDING, Order.STATUS_PAID],
                     choices=Order.STATUS_CHOICE,
                     widget=forms.CheckboxSelectMultiple,
                     required=False
                 )),
            ]
        )


@receiver(register_data_exporters, dispatch_uid="exporter_json")
def register_json_export(sender, **kwargs):
    return JSONExporter


@receiver(register_data_exporters, dispatch_uid="exporter_mail")
def register_mail_export(sender, **kwargs):
    return MailExporter
