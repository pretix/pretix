import csv
import io
from collections import OrderedDict

from django import forms
from django.utils.translation import ugettext as _

from pretix.base.exporter import BaseExporter
from pretix.base.models import Order, OrderPosition, Question


class BaseCheckinList(BaseExporter):
    pass


class CSVCheckinList(BaseCheckinList):
    name = "overview"
    identifier = 'checkinlistcsv'
    verbose_name = _('Check-in list (CSV)')

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('items',
                 forms.ModelMultipleChoiceField(
                     queryset=self.event.items.all(),
                     label=_('Limit to products'),
                     widget=forms.CheckboxSelectMultiple,
                     initial=self.event.items.filter(admission=True)
                 )),
                ('secrets',
                 forms.BooleanField(
                     label=_('Include QR-code secret'),
                     required=False
                 )),
                ('paid_only',
                 forms.BooleanField(
                     label=_('Only paid orders'),
                     initial=True,
                     required=False
                 )),
                ('sort',
                 forms.ChoiceField(
                     label=_('Sort by'),
                     initial='name',
                     choices=(
                         ('name', _('Attendee name')),
                         ('code', _('Order code')),
                     ),
                     widget=forms.RadioSelect,
                     required=False
                 )),
                ('questions',
                 forms.ModelMultipleChoiceField(
                     queryset=self.event.questions.all(),
                     label=_('Include questions'),
                     widget=forms.CheckboxSelectMultiple,
                     required=False
                 )),
            ]
        )

    def render(self, form_data: dict):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        questions = list(Question.objects.filter(event=self.event, id__in=form_data['questions']))
        qs = OrderPosition.objects.filter(
            order__event=self.event, item_id__in=form_data['items']
        ).prefetch_related(
            'answers', 'answers__question'
        ).select_related('order', 'item', 'variation')

        if form_data['sort'] == 'name':
            qs = qs.order_by('attendee_name')
        elif form_data['sort'] == 'code':
            qs = qs.order_by('order__code')

        headers = [
            _('Order code'), _('Attendee name'), _('Product'), _('Price')
        ]
        if form_data['paid_only']:
            qs = qs.filter(order__status=Order.STATUS_PAID)
        else:
            qs = qs.filter(order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING))
            headers.append(_('Paid'))

        if form_data['secrets']:
            headers.append(_('Secret'))

        for q in questions:
            headers.append(str(q.question))

        writer.writerow(headers)

        for op in qs:
            row = [
                op.order.code,
                op.attendee_name,
                str(op.item.name) + (" – " + str(op.variation.value) if op.variation else ""),
                op.price,
            ]
            if not form_data['paid_only']:
                row.append(_('Yes') if op.order.status == Order.STATUS_PAID else _('No'))
            if form_data['secrets']:
                row.append(op.secret)
            acache = {}
            for a in op.answers.all():
                acache[a.question_id] = str(a)
            for q in questions:
                row.append(acache.get(q.pk, ''))

            writer.writerow(row)

        return 'checkin.csv', 'text/csv', output.getvalue().encode("utf-8")
