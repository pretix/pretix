#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import logging
from decimal import Decimal
from typing import List

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext as _

from pretix.base.i18n import language
from pretix.base.modelimport import DataImportError, ImportColumn, parse_csv
from pretix.base.modelimport_orders import get_order_import_columns
from pretix.base.modelimport_vouchers import get_voucher_import_columns
from pretix.base.models import (
    CachedFile, Event, InvoiceAddress, LogEntry, Order, OrderPayment,
    OrderPosition, User, Voucher,
)
from pretix.base.models.orders import Transaction
from pretix.base.services.invoices import generate_invoice, invoice_qualified
from pretix.base.services.locking import lock_objects
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.signals import order_paid, order_placed
from pretix.celery_app import app

logger = logging.getLogger(__name__)


def _validate(cf: CachedFile, charset: str, cols: List[ImportColumn], settings: dict):
    try:
        parsed = parse_csv(cf.file, charset=charset)
    except UnicodeDecodeError as e:
        raise DataImportError(
            _(
                'Error decoding special characters in your file: {message}').format(
                message=str(e)
            )
        )
    data = []
    for i, record in enumerate(parsed):
        if not any(record.values()):
            continue
        values = {}
        for c in cols:
            val = c.resolve(settings, record)
            if isinstance(val, str):
                val = val.strip()
            try:
                values[c.identifier] = c.clean(val, values)
            except ValidationError as e:
                raise DataImportError(
                    _(
                        'Error while importing value "{value}" for column "{column}" in line "{line}": {message}').format(
                        value=val if val is not None else '', column=c.verbose_name, line=i + 1, message=e.message
                    )
                )
        data.append(values)
    return data


@app.task(base=ProfiledEventTask, throws=(DataImportError,))
def import_orders(event: Event, fileid: str, settings: dict, locale: str, user, charset=None) -> None:
    cf = CachedFile.objects.get(id=fileid)
    user = User.objects.get(pk=user)
    with language(locale, event.settings.region):
        cols = get_order_import_columns(event)
        data = _validate(cf, charset, cols, settings)

        if settings['orders'] == 'one' and len(data) > django_settings.PRETIX_MAX_ORDER_SIZE:
            raise DataImportError(
                _('Orders cannot have more than %(max)s positions.') % {'max': django_settings.PRETIX_MAX_ORDER_SIZE}
            )

        used_groupers = set()
        current_grouper = []
        current_order_level_data = {}
        orders = []
        order = None

        # Prepare model objects. Yes, this might consume lots of RAM, but allows us to make the actual SQL transaction
        # shorter. We'll see what works better in reality…
        lock_seats = []
        for i, record in enumerate(data):
            try:
                create_new_order = (
                    order is None or
                    settings['orders'] == 'many' or
                    (settings['orders'] == 'mixed' and record["grouping"] != current_grouper)
                )

                if create_new_order:
                    if settings['orders'] == 'mixed':
                        if record["grouping"] in used_groupers:
                            raise DataImportError(
                                _('The grouping "%(value)s" occurs on non-consecutive lines (seen again on line %(row)s).') % {
                                    "value": record["grouping"],
                                    "row": i + 1,
                                }
                            )
                        current_grouper = record["grouping"]
                        used_groupers.add(current_grouper)

                    current_order_level_data = {
                        c.identifier: record.get(c.identifier)
                        for c in cols if getattr(c, "order_level", False)
                    }
                    order = Order(
                        event=event,
                        testmode=settings['testmode'],
                    )
                    order.meta_info = {}
                    order._positions = []
                    order._address = InvoiceAddress()
                    order._address.name_parts = {'_scheme': event.settings.name_scheme}
                    orders.append(order)

                if settings['orders'] == 'mixed' and len(order._positions) >= django_settings.PRETIX_MAX_ORDER_SIZE:
                    raise DataImportError(
                        _('Orders cannot have more than %(max)s positions.') % {
                            'max': django_settings.PRETIX_MAX_ORDER_SIZE}
                    )

                position = OrderPosition(positionid=len(order._positions) + 1)
                position.attendee_name_parts = {'_scheme': event.settings.name_scheme}
                position.meta_info = {}
                order._positions.append(position)
                position.assign_pseudonymization_id()

                for c in cols:
                    value = record.get(c.identifier)
                    if getattr(c, "order_level", False) and value != current_order_level_data.get(c.identifier):
                        raise DataImportError(
                            _('Inconsistent data in row {row}: Column {col} contains value "{val_line}", but '
                              'for this order, the value has already been set to "{val_order}".').format(
                                row=i + 1,
                                col=c.verbose_name,
                                val_line=value,
                                val_order=current_order_level_data.get(c.identifier) or "",
                            )
                        )
                    c.assign(value, order, position, order._address)

                if position.seat is not None:
                    lock_seats.append((order.sales_channel, position.seat))
            except (ValidationError, ImportError) as e:
                raise DataImportError(
                    _('Invalid data in row {row}: {message}').format(row=i + 1, message=str(e))
                )

        try:
            with transaction.atomic():
                # We don't support vouchers, quotas, or memberships here, so we only need to lock if seats are in use
                if lock_seats:
                    lock_objects([s for c, s in lock_seats], shared_lock_objects=[event])
                    for c, s in lock_seats:
                        if not s.is_available(sales_channel=c):
                            raise DataImportError(_('The seat you selected has already been taken. Please select a different seat.'))

                save_transactions = []
                save_logentries = []
                for o in orders:
                    o.total = sum([c.price for c in o._positions])  # currently no support for fees
                    if o.total == Decimal('0.00'):
                        o.status = Order.STATUS_PAID
                        o.save()
                        OrderPayment.objects.create(
                            local_id=1,
                            order=o,
                            amount=Decimal('0.00'),
                            provider='free',
                            info='{}',
                            payment_date=now(),
                            state=OrderPayment.PAYMENT_STATE_CONFIRMED
                        )
                    elif settings['status'] == 'paid':
                        o.status = Order.STATUS_PAID
                        o.save()
                        OrderPayment.objects.create(
                            local_id=1,
                            order=o,
                            amount=o.total,
                            provider='manual',
                            info='{}',
                            payment_date=now(),
                            state=OrderPayment.PAYMENT_STATE_CONFIRMED
                        )
                    else:
                        o.status = Order.STATUS_PENDING
                        o.save()
                    for p in o._positions:
                        p.order = o
                        p.save()
                    o._address.order = o
                    o._address.save()
                    for c in cols:
                        c.save(o)
                    save_logentries.append(o.log_action(
                        'pretix.event.order.placed',
                        user=user,
                        data={'source': 'import'},
                        save=False,
                    ))
                    save_transactions += o.create_transactions(is_new=True, fees=[], positions=o._positions, save=False)
                Transaction.objects.bulk_create(save_transactions)
                LogEntry.bulk_create_and_postprocess(save_logentries)

            for o in orders:
                with language(o.locale, event.settings.region):
                    order_placed.send(event, order=o, bulk=True)
                    if o.status == Order.STATUS_PAID:
                        order_paid.send(event, order=o)

                    gen_invoice = invoice_qualified(o) and (
                        (event.settings.get('invoice_generate') == 'True') or
                        (event.settings.get('invoice_generate') == 'paid' and o.status == Order.STATUS_PAID)
                    ) and not o.invoices.last()
                    if gen_invoice:
                        try:
                            generate_invoice(o, trigger_pdf=True)
                        except Exception as e:
                            logger.exception("Could not generate invoice.")
                            o.log_action("pretix.event.order.invoice.failed", data={
                                "exception": str(e)
                            })
        except DataImportError:
            raise ValidationError(_('We were not able to process your request completely as the server was too busy. '
                                    'Please try again.'))
    cf.delete()


@app.task(base=ProfiledEventTask, throws=(DataImportError,))
def import_vouchers(event: Event, fileid: str, settings: dict, locale: str, user, charset=None) -> None:
    cf = CachedFile.objects.get(id=fileid)
    user = User.objects.get(pk=user)
    with language(locale, event.settings.region):
        cols = get_voucher_import_columns(event)
        data = _validate(cf, charset, cols, settings)

        # Prepare model objects. Yes, this might consume lots of RAM, but allows us to make the actual SQL transaction
        # shorter. We'll see what works better in reality…
        vouchers = []
        lock_seats = []
        for i, record in enumerate(data):
            try:
                voucher = Voucher(event=event)
                vouchers.append(voucher)

                if not record.get("code"):
                    raise ValidationError(_('A voucher cannot be created without a code.'))
                Voucher.clean_item_properties(
                    record,
                    event,
                    record.get('quota'),
                    record.get('item'),
                    record.get('variation'),
                    block_quota=record.get('block_quota')
                )
                Voucher.clean_subevent(record, event)
                Voucher.clean_max_usages(record, 0)

                for c in cols:
                    c.assign(record.get(c.identifier), voucher)

                if voucher.seat is not None:
                    lock_seats.append(voucher.seat)
            except (ValidationError, ImportError) as e:
                raise DataImportError(
                    _('Invalid data in row {row}: {message}').format(row=i, message=str(e))
                )

        with transaction.atomic():
            # We don't support quotas here, so we only need to lock if seats are in use
            if lock_seats:
                lock_objects(lock_seats, shared_lock_objects=[event])
                for s in lock_seats:
                    if not s.is_available():
                        raise DataImportError(
                            _('The seat you selected has already been taken. Please select a different seat.'))

            save_logentries = []
            for v in vouchers:
                v.save()
                save_logentries.append(v.log_action(
                    'pretix.voucher.added',
                    user=user,
                    data={'source': 'import'},
                    save=False,
                ))
                for c in cols:
                    c.save(v)
            LogEntry.bulk_create_and_postprocess(save_logentries)
    cf.delete()
