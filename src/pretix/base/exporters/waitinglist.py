from collections import OrderedDict

from django import forms
from django.db.models import F, Q
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.models.waitinglist import WaitingListEntry

from ..exporter import ListExporter
from ..signals import (
    register_data_exporters, register_multievent_data_exporters,
)


class WaitingListExporter(ListExporter):
    identifier = 'waitinglist'
    verbose_name = _('Waiting list')

    # map selected status to label and queryset-filter
    status_filters = [
        (
            '',
            _('All entries'),
            lambda qs: qs
        ),
        (
            'awaiting-voucher',
            _('Waiting for a voucher'),
            lambda qs: qs.filter(voucher__isnull=True)
        ),
        (
            'voucher-assigned',
            _('Voucher assigned'),
            lambda qs: qs.filter(voucher__isnull=False)
        ),
        (
            'awaiting-redemption',
            _('Waiting for redemption'),
            lambda qs: qs.filter(
                voucher__isnull=False,
                voucher__redeemed__lt=F('voucher__max_usages'),
            ).filter(Q(voucher__valid_until__isnull=True) | Q(voucher__valid_until__gt=now()))
        ),
        (
            'voucher-redeemed',
            _('Voucher redeemed'),
            lambda qs: qs.filter(
                voucher__isnull=False,
                voucher__redeemed__gte=F('voucher__max_usages'),
            )
        ),
        (
            'voucher-expired',
            _('Voucher expired'),
            lambda qs: qs.filter(
                voucher__isnull=False,
                voucher__redeemed__lt=F('voucher__max_usages'),
                voucher__valid_until__isnull=False,
                voucher__valid_until__lte=now()
            )
        ),
    ]

    def iterate_list(self, form_data):
        # create dicts for easier access by key, which is passed by form_data[status]
        status_labels = {k: v for k, v, c in self.status_filters}
        queryset_mutators = {k: c for k, v, c in self.status_filters}

        entries = WaitingListEntry.objects.filter(
            event__in=self.events,
        ).select_related(
            'item', 'variation', 'voucher', 'subevent'
        ).order_by('created')

        # apply filter to queryset/entries according to status
        # if unknown status-filter is given, django will handle the error
        status_filter = form_data.get("status", "")
        entries = queryset_mutators[status_filter](entries)

        headers = [
            _('Date'),
            _('Email'),
            _('Product name'),
            _('Variation'),
            _('Event slug'),
            _('Event name'),
            pgettext_lazy('subevents', 'Date'),
            _('Language'),
            _('Priority'),
            _('Status'),
            _('Voucher code'),
        ]

        yield headers
        yield self.ProgressSetTotal(total=len(entries))

        for entry in entries:
            if entry.voucher:
                if entry.voucher.redeemed >= entry.voucher.max_usages:
                    status_label = status_labels['voucher-redeemed']
                elif not entry.voucher.is_active():
                    status_label = status_labels['voucher-expired']
                else:
                    status_label = status_labels['voucher-assigned']
            else:
                status_label = status_labels['awaiting-voucher']
            row = [
                entry.created.isoformat(),
                entry.email,
                str(entry.item) if entry.item else "",
                str(entry.variation) if entry.variation else "",
                entry.event.slug,
                entry.event.name,
                str(entry.subevent) if entry.subevent else "",
                entry.locale,
                str(entry.priority),
                status_label,
                entry.voucher.code if entry.voucher else '',
            ]
            yield row

    @property
    def additional_form_fields(self):
        return OrderedDict(
            [
                ('status',
                 forms.ChoiceField(
                     label=_('Status'),
                     initial=['awaiting-voucher'],
                     required=False,
                     choices=[(k, v) for (k, v, c) in self.status_filters]
                 )),
            ]
        )

    def get_filename(self):
        if self.is_multievent:
            event = self.events.first()
            slug = event.organizer.slug if len(self.events) > 1 else event.slug
        else:
            slug = self.event.slug
        return '{}_waitinglist'.format(slug)


@receiver(register_data_exporters, dispatch_uid="exporter_waitinglist")
def register_waitinglist_exporter(sender, **kwargs):
    return WaitingListExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_waitinglist")
def register_multievent_i_waitinglist_exporter(sender, **kwargs):
    return WaitingListExporter
