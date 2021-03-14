from django.utils.translation import gettext
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Event, LogEntry, User, Voucher
from pretix.base.services.mail import mail


def vouchers_send(event: Event, vouchers: list, subject: str, message: str, recipients: list, user: int,
                  progress=None) -> None:
    vouchers = list(Voucher.objects.filter(id__in=vouchers).order_by('id'))
    user = User.objects.get(pk=user)
    for ir, r in enumerate(recipients):
        voucher_list = []
        for i in range(r['number']):
            voucher_list.append(vouchers.pop())
        with language(event.settings.locale):
            email_context = get_email_context(event=event, name=r.get('name') or '',
                                              voucher_list=[v.code for v in voucher_list])
            mail(
                r['email'],
                subject,
                LazyI18nString(message),
                email_context,
                event,
                locale=event.settings.locale,
            )
            logs = []
            for v in voucher_list:
                if r.get('tag') and r.get('tag') != v.tag:
                    v.tag = r.get('tag')
                if v.comment:
                    v.comment += '\n\n'
                v.comment = gettext('The voucher has been sent to {recipient}.').format(recipient=r['email'])
                logs.append(v.log_action(
                    'pretix.voucher.sent',
                    user=user,
                    data={
                        'recipient': r['email'],
                        'name': r.get('name'),
                        'subject': subject,
                        'message': message,
                    },
                    save=False
                ))
            Voucher.objects.bulk_update(voucher_list, fields=['comment', 'tag'], batch_size=500)
            LogEntry.objects.bulk_create(logs, batch_size=500)

            if progress and ir % 50 == 0:
                progress(ir / len(recipients))
