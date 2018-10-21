import json
from collections import OrderedDict
from io import BytesIO
from typing import Tuple

from django import forms
from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.translation import ugettext as _
from PyPDF2 import PdfFileMerger
from reportlab.lib import pagesizes
from reportlab.pdfgen import canvas

from pretix.base.exporter import BaseExporter
from pretix.base.i18n import language
from pretix.base.models import Order, OrderPosition
from pretix.base.pdf import Renderer
from pretix.plugins.badges.models import BadgeItem, BadgeLayout


def _renderer(event, layout):
    if isinstance(layout.background, File) and layout.background.name:
        bgf = default_storage.open(layout.background.name, "rb")
    else:
        bgf = open(finders.find('pretixplugins/badges/badge_default_a6l.pdf'), "rb")
    return Renderer(event, json.loads(layout.layout), bgf)


def render_pdf(event, positions):
    Renderer._register_fonts()

    renderermap = {
        bi.item_id: _renderer(event, bi.layout)
        for bi in BadgeItem.objects.select_related('layout').filter(item__event=event)
    }
    try:
        default_renderer = _renderer(event, event.badge_layouts.get(default=True))
    except BadgeLayout.DoesNotExist:
        default_renderer = None
    merger = PdfFileMerger()

    for op in positions:
        r = renderermap.get(op.item_id, default_renderer)
        if not r:
            continue

        with language(op.order.locale):
            buffer = BytesIO()
            p = canvas.Canvas(buffer, pagesize=pagesizes.A4)
            r.draw_page(p, op.order, op)
            p.save()
            outbuffer = r.render_background(buffer, 'Badge')
            merger.append(ContentFile(outbuffer.read()))

    outbuffer = BytesIO()
    merger.write(outbuffer)
    merger.close()
    outbuffer.seek(0)
    return outbuffer


class BadgeExporter(BaseExporter):
    identifier = "badges"
    verbose_name = _("Attendee badges")

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
                ('include_pending',
                 forms.BooleanField(
                     label=_('Include pending orders'),
                     required=False
                 )),
                ('order_by',
                 forms.ChoiceField(
                     label=_('Sort by'),
                     choices=(
                         ('name', _('Attendee name')),
                         ('last_name', _('Last part of attendee name')),
                     )
                 )),
            ]
        )
        return d

    def render(self, form_data: dict) -> Tuple[str, str, str]:
        qs = OrderPosition.objects.filter(
            order__event=self.event, item_id__in=form_data['items']
        ).prefetch_related(
            'answers', 'answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to')

        if form_data.get('include_pending'):
            qs = qs.filter(order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING])
        else:
            qs = qs.filter(order__status__in=[Order.STATUS_PAID])

        if form_data.get('order_by') == 'name':
            qs = qs.order_by('attendee_name_cached', 'order__code')
        elif form_data.get('order_by') == 'last_name':
            qs = qs.order_by('order__code')
            qs = sorted(qs, key=lambda op: op.attendee_name.split()[-1] if op.attendee_name else '')

        outbuffer = render_pdf(self.event, qs)
        return 'badges.pdf', 'application/pdf', outbuffer.read()
