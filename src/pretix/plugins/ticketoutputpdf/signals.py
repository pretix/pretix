#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import copy
import json

from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from pretix.base.channels import get_all_sales_channels
from pretix.base.models import Event
from pretix.base.signals import (  # NOQA: legacy import
    EventPluginSignal, event_copy_data, item_copy_data, layout_text_variables,
    logentry_display, logentry_object_link, register_data_exporters,
    register_multievent_data_exporters, register_ticket_outputs,
)
from pretix.control.signals import item_forms, order_position_buttons
from pretix.plugins.ticketoutputpdf.forms import TicketLayoutItemForm
from pretix.plugins.ticketoutputpdf.models import (
    TicketLayout, TicketLayoutItem,
)
from pretix.presale.style import (  # NOQA: legacy import
    get_fonts, register_fonts,
)


@receiver(register_ticket_outputs, dispatch_uid="output_pdf")
def register_ticket_outputs(sender, **kwargs):
    from .ticketoutput import PdfTicketOutput
    return PdfTicketOutput


@receiver(register_data_exporters, dispatch_uid="dataexport_pdf")
def register_data(sender, **kwargs):
    from .exporters import AllTicketsPDF
    return AllTicketsPDF


@receiver(register_multievent_data_exporters, dispatch_uid="dataexport_multievent_pdf")
def register_multievent_data(sender, **kwargs):
    from .exporters import AllTicketsPDF
    return AllTicketsPDF


@receiver(item_forms, dispatch_uid="pretix_ticketoutputpdf_item_forms")
def control_item_forms(sender, request, item, **kwargs):
    forms = []
    queryset = sender.ticket_layouts.all()
    for k, v in sorted(list(get_all_sales_channels().items()), key=lambda a: (int(a[0] != 'web'), a[0])):
        try:
            inst = TicketLayoutItem.objects.get(item=item, sales_channel=k)
        except TicketLayoutItem.DoesNotExist:
            inst = TicketLayoutItem(item=item)
        forms.append(TicketLayoutItemForm(
            instance=inst,
            event=sender,
            sales_channel=v,
            queryset=queryset,
            data=(request.POST if request.method == "POST" else None),
            prefix="ticketlayoutitem_{}".format(k)
        ))
    return forms


@receiver(item_copy_data, dispatch_uid="pretix_ticketoutputpdf_item_copy")
def copy_item(sender, source, target, **kwargs):
    for tli in TicketLayoutItem.objects.filter(item=source):
        TicketLayoutItem.objects.create(item=target, layout=tli.layout, sales_channel=tli.sales_channel)


@receiver(signal=event_copy_data, dispatch_uid="pretix_ticketoutputpdf_copy_data")
def pdf_event_copy_data_receiver(sender, other, item_map, question_map, **kwargs):
    if sender.ticket_layouts.exists():  # idempotency
        return
    layout_map = {}
    for bl in other.ticket_layouts.all():
        oldid = bl.pk
        bl = copy.copy(bl)
        bl.pk = None
        bl.event = sender

        layout = json.loads(bl.layout)
        for o in layout:
            if o['type'] == 'textarea':
                if o['content'].startswith('question_'):
                    try:
                        newq = question_map.get(int(o['content'][9:]))
                    except ValueError:
                        # int cannot convert new placeholders question_{identifier}
                        # can be safely ignored as only old format questions_{pk} should be converted
                        pass
                    else:
                        if newq:
                            o['content'] = 'question_{}'.format(newq.pk)
        bl.layout = json.dumps(layout)

        bl.save()

        if bl.background and bl.background.name:
            bl.background.save('background.pdf', bl.background)

        layout_map[oldid] = bl

    for bi in TicketLayoutItem.objects.filter(item__event=other):
        TicketLayoutItem.objects.create(item=item_map.get(bi.item_id), layout=layout_map.get(bi.layout_id),
                                        sales_channel=bi.sales_channel)
    return layout_map


@receiver(signal=logentry_display, dispatch_uid="pretix_ticketoutputpdf_logentry_display")
def pdf_logentry_display(sender, logentry, **kwargs):
    if not logentry.action_type.startswith('pretix.plugins.ticketoutputpdf'):
        return

    plains = {
        'pretix.plugins.ticketoutputpdf.layout.added': _('Ticket layout created.'),
        'pretix.plugins.ticketoutputpdf.layout.deleted': _('Ticket layout deleted.'),
        'pretix.plugins.ticketoutputpdf.layout.changed': _('Ticket layout changed.'),
    }

    if logentry.action_type in plains:
        return plains[logentry.action_type]


@receiver(signal=logentry_object_link, dispatch_uid="pretix_ticketoutputpdf_logentry_object_link")
def pdf_logentry_object_link(sender, logentry, **kwargs):
    if not logentry.action_type.startswith('pretix.plugins.ticketoutputpdf.layout') or not isinstance(
            logentry.content_object, TicketLayout):
        return

    a_text = _('Ticket layout {val}')
    a_map = {
        'href': reverse('plugins:ticketoutputpdf:edit', kwargs={
            'event': sender.slug,
            'organizer': sender.organizer.slug,
            'layout': logentry.content_object.id
        }),
        'val': escape(logentry.content_object.name),
    }
    a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
    return a_text.format_map(a_map)


def _ticket_layouts_for_item(request, item):
    if not hasattr(request, '_ticket_layouts_for_item'):
        request._ticket_layouts_for_item = {}
    if item.pk not in request._ticket_layouts_for_item:
        request._ticket_layouts_for_item[item.pk] = {
            tli.sales_channel: tli.layout
            for tli in item.ticketlayout_assignments.select_related('layout')
        }
        if request._ticket_layouts_for_item[item.pk] and 'web' not in request._ticket_layouts_for_item[item.pk]:
            request._ticket_layouts_for_item[item.pk]['web'] = request.event.ticket_layouts.get(default=True)

    return request._ticket_layouts_for_item[item.pk]


@receiver(order_position_buttons, dispatch_uid="pretix_ticketoutputpdf_control_order_buttons")
def control_order_position_info(sender: Event, position, request, order, **kwargs):
    if not position.generate_ticket:
        return ''

    layouts = []
    seen = set()
    lm = _ticket_layouts_for_item(request, position.item)
    if order.sales_channel in lm:
        seen.add(lm[order.sales_channel])
    for k, l in lm.items():
        if k == order.sales_channel or l in seen:
            continue
        layouts.append({
            'label': str(l.name),
            'channel': k,
        })
        seen.add(l)

    if not layouts:
        return ''

    template = get_template('pretixplugins/ticketoutputpdf/control_order_position_buttons.html')
    ctx = {
        'order': position.order,
        'request': request,
        'event': sender,
        'position': position,
        'layouts': layouts,
    }
    return template.render(ctx, request=request).strip()


override_layout = EventPluginSignal()
"""
Arguments: ``layout``, ``orderposition``

This signal allows you to forcefully override the ticket layout that is being used to create the ticket PDF. Use with
care, as this will render any specifically by the organizer selected templates useless.

The ``layout`` keyword argument will contain the layout which has been originally selected by the system, the
``orderposition`` keyword argument will contain the ``OrderPosition`` which is being generated.

If you implement this signal and do not want to override the layout, make sure to return the ``layout`` keyword argument
which you have been passed.

As with all plugin signals, the ``sender`` keyword will contain the event.
"""
