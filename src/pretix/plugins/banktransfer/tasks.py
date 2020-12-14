import logging
import re
from decimal import Decimal

import dateutil.parser
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.db import transaction
from django.db.models import Q
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


@transaction.atomic
def _handle_transaction(trans: BankTransaction, code: str, event: Event = None, organizer: Organizer = None,
                        slug: str = None):
    if event:
        try:
            trans.order = event.orders.get(code=code)
        except Order.DoesNotExist:
            normalized_code = Order.normalize_code(code)
            try:
                trans.order = event.orders.get(code=normalized_code)
            except Order.DoesNotExist:
                trans.state = BankTransaction.STATE_NOMATCH
                trans.save()
                return
    else:
        qs = Order.objects.filter(event__organizer=organizer)
        if slug:
            qs = qs.filter(event__slug__iexact=slug)
        try:
            trans.order = qs.get(code=code)
        except Order.DoesNotExist:
            normalized_code = Order.normalize_code(code)
            try:
                trans.order = qs.get(code=normalized_code)
            except Order.DoesNotExist:
                trans.state = BankTransaction.STATE_NOMATCH
                trans.save()
                return

    if trans.order.status == Order.STATUS_PAID and trans.order.pending_sum <= Decimal('0.00'):
        trans.state = BankTransaction.STATE_DUPLICATE
    elif trans.order.status == Order.STATUS_CANCELED:
        trans.state = BankTransaction.STATE_ERROR
        trans.message = gettext_noop('The order has already been canceled.')
    else:
        try:
            p, created = trans.order.payments.get_or_create(
                amount=trans.amount,
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
                defaults={
                    'state': OrderPayment.PAYMENT_STATE_CREATED,
                }
            )
        except OrderPayment.MultipleObjectsReturned:
            created = False
            p = trans.order.payments.filter(
                amount=trans.amount,
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
            ).last()

        p.info_data = {
            'reference': trans.reference,
            'date': trans.date_parsed.isoformat() if trans.date_parsed else trans.date,
            'payer': trans.payer,
            'iban': trans.iban,
            'bic': trans.bic,
            'trans_id': trans.pk
        }

        if created:
            # We're perform a payment method switching on-demand here
            old_fee, new_fee, fee, p = change_payment_provider(trans.order, p.payment_provider, p.amount,
                                                               new_payment=p, create_log=False)  # noqa
            if fee:
                p.fee = fee
                p.save(update_fields=['fee'])

        try:
            p.confirm()
        except Quota.QuotaExceededException:
            trans.state = BankTransaction.STATE_VALID
            cancel_old_payments(trans.order)
        except SendMailException:
            trans.state = BankTransaction.STATE_VALID
            cancel_old_payments(trans.order)
        else:
            trans.state = BankTransaction.STATE_VALID
            cancel_old_payments(trans.order)

            o = trans.order
            o.refresh_from_db()
            if o.pending_sum > Decimal('0.00') and o.status == Order.STATUS_PENDING:
                notify_incomplete_payment(o)

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
            prefixes = []

            try:
                # Delete left-over transactions from a failed run before so they can reimported
                BankTransaction.objects.filter(state=BankTransaction.STATE_UNCHECKED, **job.owner_kwargs).delete()

                transactions = _get_unknown_transactions(job, data, **job.owner_kwargs)

                code_len = settings.ENTROPY['order_code']
                if job.event:
                    pattern = re.compile(job.event.slug.upper() + r"[ \-_]*([A-Z0-9]{%s})" % code_len)
                else:
                    if not prefixes:
                        prefixes = [e.slug.upper().replace(".", r"\.").replace("-", r"[\- ]*")
                                    for e in job.organizer.events.all()]
                    pattern = re.compile("(%s)[ \\-_]*([A-Z0-9]{%s})" % ("|".join(prefixes), code_len))

                for trans in transactions:
                    match = pattern.search(trans.reference.replace(" ", "").replace("\n", "").upper())

                    if match:
                        if job.event:
                            code = match.group(1)
                            _handle_transaction(trans, code, event=job.event)
                        else:
                            slug = match.group(1)
                            code = match.group(2)
                            _handle_transaction(trans, code, organizer=job.organizer, slug=slug)
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
