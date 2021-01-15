import logging
import re
from decimal import Decimal

import dateutil.parser
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.db import transaction
from django.db.models import Max, Min, Q
from django.db.models.functions import Length
from django.utils.translation import gettext, gettext_noop
from django_scopes import scope, scopes_disabled

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Event, Order, OrderPayment, Organizer, Quota
from pretix.base.payment import PaymentException
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import change_payment_provider
from pretix.base.services.tasks import TransactionAwareTask
from pretix.celery_app import app

from .models import BankImportJob, BankTransaction

logger = logging.getLogger(__name__)


def notify_incomplete_payment(o: Order):
    with language(o.locale, o.event.settings.region):
        email_template = o.event.settings.mail_text_order_expire_warning
        email_context = get_email_context(event=o.event, order=o)
        email_subject = gettext('Your order received an incomplete payment: %(code)s') % {'code': o.code}

        try:
            o.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.expire_warning_sent'
            )
        except SendMailException:
            logger.exception('Reminder email could not be sent')


def cancel_old_payments(order):
    for p in order.payments.filter(
        state__in=(OrderPayment.PAYMENT_STATE_PENDING,
                   OrderPayment.PAYMENT_STATE_CREATED),
        provider='banktransfer',
    ):
        try:
            with transaction.atomic():
                p.payment_provider.cancel_payment(p)
                order.log_action('pretix.event.order.payment.canceled', {
                    'local_id': p.local_id,
                    'provider': p.provider,
                })
        except PaymentException as e:
            order.log_action(
                'pretix.event.order.payment.canceled.failed',
                {
                    'local_id': p.local_id,
                    'provider': p.provider,
                    'error': str(e)
                },
            )


def _find_order_for_code(base_qs, code):
    try_codes = [
        code,
        Order.normalize_code(code, is_fallback=True),
        code[:settings.ENTROPY['order_code']],
        Order.normalize_code(code[:settings.ENTROPY['order_code']], is_fallback=True)
    ]
    for c in try_codes:
        try:
            return base_qs.get(code=c)
        except Order.DoesNotExist:
            pass


@transaction.atomic
def _handle_transaction(trans: BankTransaction, matches: tuple, event: Event = None, organizer: Organizer = None):
    orders = []
    if event:
        for slug, code in matches:
            order = _find_order_for_code(event.orders, code)
            if order and order.code not in {o.code for o in orders}:
                orders.append(order)
    else:
        qs = Order.objects.filter(event__organizer=organizer)
        for slug, code in matches:
            order = _find_order_for_code(qs.filter(event__slug__iexact=slug), code)
            if order and order.code not in {o.code for o in orders}:
                orders.append(order)

    if not orders:
        # No match
        trans.state = BankTransaction.STATE_NOMATCH
        trans.save()
        return
    else:
        trans.order = orders[0]

    for o in orders:
        if o.status == Order.STATUS_PAID and o.pending_sum <= Decimal('0.00'):
            trans.state = BankTransaction.STATE_DUPLICATE
            trans.save()
            return
        elif o.status == Order.STATUS_CANCELED:
            trans.state = BankTransaction.STATE_ERROR
            trans.message = gettext_noop('The order has already been canceled.')
            trans.save()
            return

    if len(orders) > 1:
        # Multi-match! Can we split this automatically?
        order_pending_sum = sum(o.pending_sum for o in orders)
        if order_pending_sum != trans.amount:
            # we can't :( this needs to be dealt with by a human
            trans.state = BankTransaction.STATE_NOMATCH
            trans.message = gettext_noop('Automatic split to multiple orders not possible.')
            trans.save()
            return

        # we can!
        splits = [(o, o.pending_sum) for o in orders]
    else:
        splits = [(orders[0], trans.amount)]

    trans.state = BankTransaction.STATE_VALID
    for order, amount in splits:
        try:
            p, created = order.payments.get_or_create(
                amount=amount,
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
                defaults={
                    'state': OrderPayment.PAYMENT_STATE_CREATED,
                }
            )
        except OrderPayment.MultipleObjectsReturned:
            created = False
            p = order.payments.filter(
                amount=amount,
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
            ).last()

        p.info_data = {
            'reference': trans.reference,
            'date': trans.date_parsed.isoformat() if trans.date_parsed else trans.date,
            'payer': trans.payer,
            'iban': trans.iban,
            'bic': trans.bic,
            'full_amount': str(trans.amount),
            'trans_id': trans.pk
        }

        if created:
            # We're perform a payment method switching on-demand here
            old_fee, new_fee, fee, p = change_payment_provider(order, p.payment_provider, p.amount,
                                                               new_payment=p, create_log=False)  # noqa
            if fee:
                p.fee = fee
                p.save(update_fields=['fee'])

        try:
            p.confirm()
        except Quota.QuotaExceededException:
            # payment confirmed but order status could not be set, no longer problem of this plugin
            cancel_old_payments(order)
        except SendMailException:
            # payment confirmed but order status could not be set, no longer problem of this plugin
            cancel_old_payments(order)
        else:
            cancel_old_payments(order)

            order.refresh_from_db()
            if order.pending_sum > Decimal('0.00') and order.status == Order.STATUS_PENDING:
                notify_incomplete_payment(order)

    trans.save()


def parse_date(date_str):
    try:
        return dateutil.parser.parse(
            date_str,
            dayfirst="." in date_str,
        ).date()
    except (ValueError, OverflowError):
        pass
    return None


def _get_unknown_transactions(job: BankImportJob, data: list, event: Event = None, organizer: Organizer = None):
    amount_pattern = re.compile("[^0-9.-]")
    known_checksums = set(t['checksum'] for t in BankTransaction.objects.filter(
        Q(event=event) if event else Q(organizer=organizer)
    ).values('checksum'))

    transactions = []
    for row in data:
        amount = row['amount']
        if not isinstance(amount, Decimal):
            if ',' in amount and '.' in amount:
                # Handle thousand-seperator , or .
                if amount.find(',') < amount.find('.'):
                    amount = amount.replace(',', '')
                else:
                    amount = amount.replace('.', '')
            amount = amount_pattern.sub("", amount.replace(',', '.'))
            try:
                amount = Decimal(amount)
            except:
                logger.exception('Could not parse amount of transaction: {}'.format(amount))
                amount = Decimal("0.00")

        trans = BankTransaction(event=event, organizer=organizer, import_job=job,
                                payer=row.get('payer', ''),
                                reference=row['reference'],
                                amount=amount, date=row['date'],
                                iban=row.get('iban', ''), bic=row.get('bic', ''))

        trans.date_parsed = parse_date(trans.date)

        trans.checksum = trans.calculate_checksum()
        if trans.checksum not in known_checksums:
            trans.state = BankTransaction.STATE_UNCHECKED
            trans.save()
            transactions.append(trans)
            known_checksums.add(trans.checksum)

    return transactions


@app.task(base=TransactionAwareTask, bind=True, max_retries=5, default_retry_delay=1)
def process_banktransfers(self, job: int, data: list) -> None:
    with language("en"):  # We'll translate error messages at display time
        with scopes_disabled():
            job = BankImportJob.objects.get(pk=job)
        with scope(organizer=job.organizer or job.event.organizer):
            job.state = BankImportJob.STATE_RUNNING
            job.save()

            try:
                # Delete left-over transactions from a failed run before so they can reimported
                BankTransaction.objects.filter(state=BankTransaction.STATE_UNCHECKED, **job.owner_kwargs).delete()

                transactions = _get_unknown_transactions(job, data, **job.owner_kwargs)

                code_len_agg = Order.objects.filter(event__organizer=job.organizer).annotate(
                    clen=Length('code')
                ).aggregate(min=Min('clen'), max=Max('clen'))
                if job.event:
                    prefixes = [job.event.slug.upper()]
                else:
                    prefixes = [e.slug.upper()
                                for e in job.organizer.events.all()]
                pattern = re.compile(
                    "(%s)[ \\-_]*([A-Z0-9]{%s,%s})" % (
                        "|".join(p.replace(".", r"\.").replace("-", r"[\- ]*") for p in prefixes),
                        code_len_agg['min'] or 0,
                        code_len_agg['max'] or 5
                    )
                )

                for trans in transactions:
                    matches = pattern.findall(trans.reference.replace(" ", "").replace("\n", "").upper())

                    if matches:
                        if job.event:
                            _handle_transaction(trans, matches, event=job.event)
                        else:
                            _handle_transaction(trans, matches, organizer=job.organizer)
                    else:
                        trans.state = BankTransaction.STATE_NOMATCH
                        trans.save()
            except LockTimeoutException:
                try:
                    self.retry()
                except MaxRetriesExceededError:
                    logger.exception('Maximum number of retries exceeded for task.')
                    job.state = BankImportJob.STATE_ERROR
                    job.save()
            except Exception as e:
                job.state = BankImportJob.STATE_ERROR
                job.save()
                raise e
            else:
                job.state = BankImportJob.STATE_COMPLETED
                job.save()
