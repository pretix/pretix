import logging
from smtplib import SMTPRecipientsRefused, SMTPSenderRefused

from django.core.mail.backends.smtp import EmailBackend
from django.utils.translation import ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea

from pretix.base.validators import PlaceholderValidator

logger = logging.getLogger('pretix.base.email')


class CustomSMTPBackend(EmailBackend):
    def test(self, from_addr):
        try:
            self.open()
            self.connection.ehlo_or_helo_if_needed()
            self.connection.rcpt("test@example.org")
            (code, resp) = self.connection.mail(from_addr, [])
            if code != 250:
                logger.warn('Error testing mail settings, code %d, resp: %s' % (code, resp))
                raise SMTPSenderRefused(code, resp, from_addr)
            senderrs = {}
            (code, resp) = self.connection.rcpt('test@example.com')
            if (code != 250) and (code != 251):
                logger.warn('Error testing mail settings, code %d, resp: %s' % (code, resp))
                raise SMTPRecipientsRefused(senderrs)
        finally:
            self.close()


class MailTemplateRenderer:
    def __init__(self, placeholders: list):
        self.placeholders = placeholders

    def formfield(self, **kwargs):
        defaults = {
            'required': False,
            'widget': I18nTextarea,
            'validators': [],
            'help_text': ''
        }
        defaults.update(kwargs)
        if defaults['help_text']:
            defaults['help_text'] += ' '
        defaults['help_text'] += _('Available placeholders: {list}').format(
            list=', '.join(['{' + v + '}' for v in self.placeholders])
        )
        defaults['validators'].append(PlaceholderValidator(['{' + v + '}' for v in self.placeholders]))
        return I18nFormField(**defaults)

    def preview(self, text, **kwargs):
        return text.format(**kwargs)

    def render(self, text, values):
        set_placeholders = set(values.keys())
        expected_palceholders = set(self.placeholders)
        if set_placeholders != expected_palceholders:
            raise ValueError('Invalid placeholder set. Unknown placeholders: {}. Missing placeholders: {}'.format(
                set_placeholders - expected_palceholders, expected_palceholders - set_placeholders
            ))

        return text.format_map(values)


mail_text_order_placed = MailTemplateRenderer(
    ['event', 'total', 'currency', 'date', 'payment_info', 'url', 'invoice_name', 'invoice_company']
)
mail_text_order_paid = MailTemplateRenderer(
    ['event', 'url', 'invoice_name', 'invoice_company', 'payment_info']
)
mail_text_order_free = MailTemplateRenderer(
    ['event', 'url', 'invoice_name', 'invoice_company']
)
mail_text_order_changed = MailTemplateRenderer(
    ['event', 'url', 'invoice_name', 'invoice_company']
)
mail_text_resend_link = MailTemplateRenderer(
    ['event', 'url', 'invoice_name', 'invoice_company']
)
mail_text_resend_all_links = MailTemplateRenderer(
    ['event', 'orders']
)
mail_text_order_expire_warning = MailTemplateRenderer(
    ['event', 'url', 'expire_date', 'invoice_name', 'invoice_company']
)
mail_text_waiting_list = MailTemplateRenderer(
    ['event', 'url', 'product', 'hours', 'code']
)
mail_text_order_canceled = MailTemplateRenderer(
    ['event', 'url', 'code']
)
mail_text_order_custom_mail = MailTemplateRenderer(
    ['expire_date', 'event', 'code', 'date', 'url', 'invoice_name', 'invoice_company']
)
mail_text_download_reminder = MailTemplateRenderer(
    ['event', 'url']
)
