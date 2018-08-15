import logging
from smtplib import SMTPRecipientsRefused, SMTPSenderRefused

import bleach
import markdown
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, Order
from pretix.base.signals import register_html_mail_renderers
from pretix.base.templatetags.rich_text import markdown_compile

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


class BaseHTMLMailRenderer:
    """
    This is the base class for all HTML e-mail renderers.
    """

    def __init__(self, event: Event):
        self.event = event

    def __str__(self):
        return self.identifier

    def render(self, plain_body: str, plain_signature: str, subject: str, order: str) -> str:
        """
        This method should generate the HTML part of the email.
        """
        raise NotImplementedError()

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this renderer. This should be short but self-explanatory.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this renderer.
        This should only contain lowercase letters and in most cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def thumbnail_filename(self) -> str:
        """
        A file name discoverable in the static file storage that contains a preview of your renderer. This should
        be a square.
        """
        raise NotImplementedError()  # NOQA

    @property
    def is_available(self) -> bool:
        """
        This renderer will only be available if this returns True. You can use this to limit this renderer
        to certain events.
        """
        return True


class ClassicMailRenderer(BaseHTMLMailRenderer):
    verbose_name = _('Classic pretix design')
    identifier = 'classic'
    thumbnail_filename = ''

    def render(self, plain_body: str, plain_signature: str, subject: str, order: Order) -> str:
        body_md = bleach.linkify(markdown_compile(plain_body))
        htmlctx = {
            'site': settings.PRETIX_INSTANCE_NAME,
            'site_url': settings.SITE_URL,
            'body': body_md,
            'color': '#8E44B3'
        }
        if self.event:
            htmlctx['event'] = self.event
            htmlctx['color'] = self.event.settings.primary_color

        if plain_signature:
            signature_md = plain_signature.replace('\n', '<br>\n')
            signature_md = bleach.linkify(bleach.clean(markdown.markdown(signature_md), tags=bleach.ALLOWED_TAGS + ['p', 'br']))
            htmlctx['signature'] = signature_md

        if order:
            htmlctx['order'] = order

        tpl = get_template('pretixbase/email/plainwrapper.html')
        body_html = tpl.render(htmlctx)
        return body_html


@receiver(register_html_mail_renderers, dispatch_uid="pretixbase_email_renderers")
def base_renderers(sender, **kwargs):
    return [ClassicMailRenderer]
