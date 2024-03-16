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
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext as _

from pretix.base.i18n import language
from pretix.base.modelimport import DataImportError, parse_csv
from pretix.base.modelimport_orders import get_order_import_columns
from pretix.base.models import (
    CachedFile, Event, InvoiceAddress, Order, OrderPayment, OrderPosition,
    User,
)
from pretix.base.models.orders import Transaction
from pretix.base.services.invoices import generate_invoice, invoice_qualified
from pretix.base.services.locking import lock_objects
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.signals import order_paid, order_placed
from pretix.celery_app import app


@app.task(base=ProfiledEventTask, throws=(DataImportError,))
def import_orders(event: Event, fileid: str, settings: dict, locale: str, user, charset=None) -> None:
    cf = CachedFile.objects.get(id=fileid)
    user = User.objects.get(pk=user)
    with language(locale, event.settings.region):
        cols = get_order_import_columns(event)
        try:
            parsed = parse_csv(cf.file, charset=charset)
        except UnicodeDecodeError as e:
            raise DataImportError(
                _(
                    'Error decoding special characters in your file: {message}').format(
                    message=str(e)
                )
            )
        orders = []
        order = None
        data = []

        # Run validation
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

        if settings['orders'] == 'one' and len(data) > django_settings.PRETIX_MAX_ORDER_SIZE:
            raise DataImportError(
                _('Orders cannot have more than %(max)s positions.') % {'max': django_settings.PRETIX_MAX_ORDER_SIZE}
            )

        # Prepare model objects. Yes, this might consume lots of RAM, but allows us to make the actual SQL transaction
        # shorter. We'll see what works better in reality…
        lock_seats = []
        for i, record in enumerate(data):
            try:
                if order is None or settings['orders'] == 'many':
                    order = Order(
                        event=event,
                        testmode=settings['testmode'],
                    )
                    order.meta_info = {}
                    order._positions = []
                    order._address = InvoiceAddress()
                    order._address.name_parts = {'_scheme': event.settings.name_scheme}
                    orders.append(order)

                position = OrderPosition(positionid=len(order._positions) + 1)
                position.attendee_name_parts = {'_scheme': event.settings.name_scheme}
                position.meta_info = {}
                if position.seat is not None:
                    lock_seats.append(position.seat)
                order._positions.append(position)
                position.assign_pseudonymization_id()

                for c in cols:
                    c.assign(record.get(c.identifier), order, position, order._address)

            except ImportError as e:
                raise ImportError(
                    _('Invalid data in row {row}: {message}').format(row=i, message=str(e))
                )

        try:
            with transaction.atomic():
                # We don't support vouchers, quotas, or memberships here, so we only need to lock if seats are in use
                if lock_seats:
                    lock_objects(lock_seats, shared_lock_objects=[event])
                    for s in lock_seats:
                        if not s.is_available():
                            raise ImportError(_('The seat you selected has already been taken. Please select a different seat.'))

                save_transactions = []
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
                    o.log_action(
                        'pretix.event.order.placed',
                        user=user,
                        data={'source': 'import'}
                    )
                    save_transactions += o.create_transactions(is_new=True, fees=[], positions=o._positions, save=False)
                Transaction.objects.bulk_create(save_transactions)

            for o in orders:
                with language(o.locale, event.settings.region):
                    order_placed.send(event, order=o)
                    if o.status == Order.STATUS_PAID:
                        order_paid.send(event, order=o)

                    gen_invoice = invoice_qualified(o) and (
                        (event.settings.get('invoice_generate') == 'True') or
                        (event.settings.get('invoice_generate') == 'paid' and o.status == Order.STATUS_PAID)
                    ) and not o.invoices.last()
                    if gen_invoice:
                        generate_invoice(o, trigger_pdf=True)
        except DataImportError:
            raise ValidationError(_('We were not able to process your request completely as the server was too busy. '
                                    'Please try again.'))
    cf.delete()
