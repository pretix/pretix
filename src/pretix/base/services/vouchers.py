from django.utils.translation import gettext
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Event, User, Voucher
from pretix.base.services.mail import mail
from pretix.base.services.tasks import TransactionAwareProfiledEventTask
from pretix.celery_app import app


@app.task(base=TransactionAwareProfiledEventTask, acks_late=True)
def vouchers_send(event: Event, vouchers: list, subject: str, message: str, recipients: list, user: int) -> None:
    vouchers = list(Voucher.objects.filter(id__in=vouchers).order_by('id'))
    user = User.objects.get(pk=user)
    for r in recipients:
        voucher_list = []
        for i in range(r['number']):
            voucher_list.append(vouchers.pop())
        with language(event.settings.locale):
            email_context = get_email_context(event=event, name=r.get('name') or '', voucher_list=[v.code for v in voucher_list])
            mail(
                r['email'],
                subject,
                LazyI18nString(message),
                email_context,
                event,
                locale=event.settings.locale,
            )
            for v in voucher_list:
                if r.get('tag') and r.get('tag') != v.tag:
                    v.tag = r.get('tag')
                if v.comment:
                    v.comment += '\n\n'
                v.comment = gettext('The voucher has been sent to {recipient}.').format(recipient=r['email'])
                v.recipient = r['email']
                v.save(update_fields=['tag', 'comment', 'recipient'])
                v.log_action(
                    'pretix.voucher.sent',
                    user=user,
                    data={
                        'recipient': r['email'],
                        'name': r.get('name'),
                        'subject': subject,
                        'message': message,
                    }
                )


@app.task(base=TransactionAwareProfiledEventTask, acks_late=True)
def vouchers_resend(event: Event, vouchers: list, user: int) -> None:
    vouchers = list(Voucher.objects.filter(id__in=vouchers).order_by('id'))
    user = User.objects.get(pk=user)
    for v in vouchers:
        with language(event.settings.locale):
            recipient = v.recipient
            # FIXME We can't get the original name
            name = ''
            # FIXME We can't get the original subject
            subject = gettext('Resent Voucher')
            # FIXME We can't get the original message
            message = LazyI18nString('We are resending you your voucher for {event}: {voucher_list}')
            email_context = get_email_context(event=event, name=name, voucher_list=[v.code])
            mail(
                recipient,
                subject,
                message,
                email_context,
                event,
                locale=event.settings.locale,
            )
            v.log_action(
                'pretix.voucher.sent',
                user=user,
                data={
                    'recipient': recipient,
                    'name': name,
                    'subject': subject,
                    'message': message,
                }
            )
