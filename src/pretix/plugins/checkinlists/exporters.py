import io
from collections import OrderedDict

import dateutil.parser
from defusedcsv import csv
from django import forms
from django.db.models import Max, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils.formats import date_format
from django.utils.timezone import is_aware, make_aware
from django.utils.translation import pgettext, ugettext as _, ugettext_lazy
from pytz import UTC
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from pretix.base.exporter import BaseExporter
from pretix.base.models import Checkin, Order, OrderPosition, Question
from pretix.base.templatetags.money import money_filter
from pretix.plugins.reports.exporters import ReportlabExportMixin


class BaseCheckinList(BaseExporter):
    @property
    def export_form_fields(self):
        d = OrderedDict(
            [
                ('list',
                 forms.ModelChoiceField(
                     queryset=self.event.checkin_lists.all(),
                     label=_('Check-in list'),
                     widget=forms.RadioSelect(
                         attrs={'class': 'scrolling-choice'}
                     ),
                     initial=self.event.checkin_lists.first()
                 )),
                ('secrets',
                 forms.BooleanField(
                     label=_('Include QR-code secret'),
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
        return d


class CBFlowable(Flowable):
    def __init__(self, checked=False):
        self.checked = checked
        super().__init__()

    def draw(self):
        self.canv.rect(1 * mm, -4.5 * mm, 4 * mm, 4 * mm)
        if self.checked:
            self.canv.line(1.5 * mm, -4.0 * mm, 4.5 * mm, -1.0 * mm)
            self.canv.line(1.5 * mm, -1.0 * mm, 4.5 * mm, -4.0 * mm)


class TableTextRotate(Flowable):
    def __init__(self, text):
        Flowable.__init__(self)
        self.text = text

    def draw(self):
        canvas = self.canv
        canvas.rotate(90)
        canvas.drawString(0, -1, self.text)


class PDFCheckinList(ReportlabExportMixin, BaseCheckinList):
    name = "overview"
    identifier = 'checkinlistpdf'
    verbose_name = ugettext_lazy('Check-in list (PDF)')

    @property
    def export_form_fields(self):
        f = super().export_form_fields
        del f['secrets']
        return f

    @property
    def pagesize(self):
        from reportlab.lib import pagesizes

        return pagesizes.landscape(pagesizes.A4)

    def get_story(self, doc, form_data):
        cl = self.event.checkin_lists.get(pk=form_data['list'])

        questions = list(Question.objects.filter(event=self.event, id__in=form_data['questions']))

        headlinestyle = self.get_style()
        headlinestyle.fontSize = 15
        headlinestyle.fontName = 'OpenSansBd'
        colwidths = [3 * mm, 8 * mm, 8 * mm] + [
            a * (doc.width - 8 * mm)
            for a in [.1, .25, (.25 if questions else .60)] + (
                [.35 / len(questions)] * len(questions) if questions else []
            )
        ]
        tstyledata = [
            ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
            ('ALIGN', (2, 0), (2, 0), 'CENTER'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'OpenSansBd'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('TEXTCOLOR', (0, 0), (0, -1), '#990000'),
            ('FONTNAME', (0, 0), (0, -1), 'OpenSansBd'),
        ]

        story = [
            Paragraph(
                '{} – {}'.format(cl.name, (cl.subevent or self.event).get_date_from_display()),
                headlinestyle
            ),
            Spacer(1, 5 * mm)
        ]

        tdata = [
            [
                '',
                '',
                # Translators: maximum 5 characters
                TableTextRotate(pgettext('tablehead', 'paid')),
                _('Order'),
                _('Name'),
                _('Product') + '\n' + _('Price'),
            ],
        ]

        for q in questions:
            tdata[0].append(str(q.question))

        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=cl.pk
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')

        qs = OrderPosition.objects.filter(
            order__event=self.event,
        ).annotate(
            last_checked_in=Subquery(cqs)
        ).select_related('item', 'variation', 'order', 'addon_to', 'order__invoice_address').prefetch_related(
            'answers', 'answers__question'
        )

        if not cl.all_products:
            qs = qs.filter(item__in=cl.limit_products.values_list('id', flat=True))

        if cl.subevent:
            qs = qs.filter(subevent=cl.subevent)

        if form_data['sort'] == 'name':
            qs = qs.order_by(Coalesce('attendee_name', 'addon_to__attendee_name', 'order__invoice_address__name'),
                             'order__code')
        elif form_data['sort'] == 'code':
            qs = qs.order_by('order__code')

        if not cl.include_pending:
            qs = qs.filter(order__status=Order.STATUS_PAID)
        else:
            qs = qs.filter(order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING))

        for op in qs:
            try:
                ian = op.order.invoice_address.name
                iac = op.order.invoice_address.company
            except:
                ian = ""
                iac = ""

            name = op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '') or ian
            if iac:
                name += "\n" + iac

            row = [
                '!!' if op.item.checkin_attention else '',
                CBFlowable(bool(op.last_checked_in)),
                '✘' if op.order.status != Order.STATUS_PAID else '✔',
                op.order.code,
                name,
                str(op.item.name) + (" – " + str(op.variation.value) if op.variation else "") + "\n" +
                money_filter(op.price, self.event.currency),
            ]
            acache = {}
            for a in op.answers.all():
                acache[a.question_id] = str(a)
            for q in questions:
                row.append(acache.get(q.pk, ''))
            if op.order.status != Order.STATUS_PAID:
                tstyledata += [
                    ('BACKGROUND', (2, len(tdata)), (2, len(tdata)), '#990000'),
                    ('TEXTCOLOR', (2, len(tdata)), (2, len(tdata)), '#ffffff'),
                    ('ALIGN', (2, len(tdata)), (2, len(tdata)), 'CENTER'),
                ]
            tdata.append(row)

        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))
        story.append(table)
        return story


class CSVCheckinList(BaseCheckinList):
    name = "overview"
    identifier = 'checkinlistcsv'
    verbose_name = ugettext_lazy('Check-in list (CSV)')

    def render(self, form_data: dict):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")
        cl = self.event.checkin_lists.get(pk=form_data['list'])

        questions = list(Question.objects.filter(event=self.event, id__in=form_data['questions']))

        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=cl.pk
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')
        qs = OrderPosition.objects.filter(
            order__event=self.event,
        ).annotate(
            last_checked_in=Subquery(cqs)
        ).prefetch_related(
            'answers', 'answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to')

        if not cl.all_products:
            qs = qs.filter(item__in=cl.limit_products.values_list('id', flat=True))

        if cl.subevent:
            qs = qs.filter(subevent=cl.subevent)

        if form_data['sort'] == 'name':
            qs = qs.order_by(Coalesce('attendee_name', 'addon_to__attendee_name'))
        elif form_data['sort'] == 'code':
            qs = qs.order_by('order__code')

        headers = [
            _('Order code'), _('Attendee name'), _('Product'), _('Price'), _('Checked in')
        ]
        if not cl.include_pending:
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
            last_checked_in = None
            if isinstance(op.last_checked_in, str):  # SQLite
                last_checked_in = dateutil.parser.parse(op.last_checked_in)
            elif op.last_checked_in:
                last_checked_in = op.last_checked_in
            if last_checked_in and not is_aware(last_checked_in):
                last_checked_in = make_aware(last_checked_in, UTC)
            row = [
                op.order.code,
                op.attendee_name or (op.addon_to.attendee_name if op.addon_to else ''),
                str(op.item.name) + (" – " + str(op.variation.value) if op.variation else ""),
                op.price,
                date_format(last_checked_in.astimezone(self.event.timezone), 'SHORT_DATETIME_FORMAT')
                if last_checked_in else ''
            ]
            if cl.include_pending:
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

        return '{}_checkin.csv'.format(self.event.slug), 'text/csv', output.getvalue().encode("utf-8")
