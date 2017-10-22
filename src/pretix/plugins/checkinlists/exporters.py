import io
from collections import OrderedDict

from defusedcsv import csv
from django import forms
from django.db.models.functions import Coalesce
from django.utils.translation import (
    pgettext, pgettext_lazy, ugettext as _, ugettext_lazy,
)

from pretix.base.exporter import BaseExporter
from pretix.base.models import Order, OrderPosition, Question


class BaseCheckinList(BaseExporter):
    pass


class CSVCheckinList(BaseCheckinList):
    name = "overview"
    identifier = 'checkinlistcsv'
    verbose_name = ugettext_lazy('Check-in list (CSV)')

    @property
    def export_form_fields(self):
        d = OrderedDict(
            [
                ('items',
                 forms.ModelMultipleChoiceField(
                     queryset=self.event.items.all(),
                     label=_('Limit to products'),
                     widget=forms.CheckboxSelectMultiple(
                         attrs={'class': 'scrolling-multiple-choice'}
                     ),
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
                     widget=forms.CheckboxSelectMultiple(
                         attrs={'class': 'scrolling-multiple-choice'}
                     ),
                     required=False
                 )),
            ]
        )
        if self.event.has_subevents:
            d['subevent'] = forms.ModelChoiceField(
                self.event.subevents.all(),
                label=pgettext_lazy('subevent', 'Date'),
                required=False,
                empty_label=pgettext_lazy('subevent', 'All dates')
            )
        return d

    def render(self, form_data: dict):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        questions = list(Question.objects.filter(event=self.event, id__in=form_data['questions']))
        qs = OrderPosition.objects.filter(
            order__event=self.event, item_id__in=form_data['items']
        ).prefetch_related(
            'answers', 'answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to')

        if form_data['sort'] == 'name':
            qs = qs.order_by(Coalesce('attendee_name', 'addon_to__attendee_name'))
        elif form_data['sort'] == 'code':
            qs = qs.order_by('order__code')

        headers = [
            _('Order code'), _('Attendee name'), _('Product'), _('Price')
        ]
        if form_data.get('subevent'):
            qs = qs.filter(subevent=form_data.get('subevent'))
        if form_data['paid_only']:
            qs = qs.filter(order__status=Order.STATUS_PAID)
        else:
            qs = qs.filter(order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING))
            headers.append(_('Paid'))

        if form_data['secrets']:
            headers.append(_('Secret'))

        if self.event.settings.attendee_emails_asked:
            headers.append(_('E-mail'))

        if self.event.has_subevents:
            headers.append(pgettext('subevent', 'Date'))

        for q in questions:
            headers.append(str(q.question))

        writer.writerow(headers)

        for op in qs:
            row = [
                op.order.code,
                op.attendee_name or (op.addon_to.attendee_name if op.addon_to else ''),
                str(op.item.name) + (" – " + str(op.variation.value) if op.variation else ""),
                op.price,
            ]
            if not form_data['paid_only']:
                row.append(_('Yes') if op.order.status == Order.STATUS_PAID else _('No'))
            if form_data['secrets']:
                row.append(op.secret)
            if self.event.settings.attendee_emails_asked:
                row.append(op.attendee_email or (op.addon_to.attendee_email if op.addon_to else ''))
            if self.event.has_subevents:
                row.append(str(op.subevent))
            acache = {}
            for a in op.answers.all():
                acache[a.question_id] = str(a)
            for q in questions:
                row.append(acache.get(q.pk, ''))

            writer.writerow(row)

        return 'checkin.csv', 'text/csv', output.getvalue().encode("utf-8")
