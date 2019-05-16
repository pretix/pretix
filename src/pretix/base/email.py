import logging
from smtplib import SMTPResponseException

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from inlinestyler.utils import inline_css

from pretix.base.models import Event, Order, OrderPosition
from pretix.base.signals import register_html_mail_renderers
from pretix.base.templatetags.rich_text import markdown_compile_email

logger = logging.getLogger('pretix.base.email')


class CustomSMTPBackend(EmailBackend):

    def test(self, from_addr):
        try:
            self.open()
            self.connection.ehlo_or_helo_if_needed()
            (code, resp) = self.connection.mail(from_addr, [])
            if code != 250:
                logger.warn('Error testing mail settings, code %d, resp: %s' % (code, resp))
                raise SMTPResponseException(code, resp)
            (code, resp) = self.connection.rcpt('testdummy@pretix.eu')
            if (code != 250) and (code != 251):
                logger.warn('Error testing mail settings, code %d, resp: %s' % (code, resp))
                raise SMTPResponseException(code, resp)
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

    def render(self, plain_body: str, plain_signature: str, subject: str, order: Order=None,
               position: OrderPosition=None) -> str:
        """
        This method should generate the HTML part of the email.

        :param plain_body: The body of the email in plain text.
        :param plain_signature: The signature with event organizer contact details in plain text.
        :param subject: The email subject.
        :param order: The order if this email is connected to one, otherwise ``None``.
        :param position: The order position if this email is connected to one, otherwise ``None``.
        :return: An HTML string
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
        This should only contain lowercase letters and in most cases will be the same as your package name or prefixed
        with your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def thumbnail_filename(self) -> str:
        """
        A file name discoverable in the static file storage that contains a preview of your renderer. This should
        be with aspect resolution 4:3.
        """
        raise NotImplementedError()  # NOQA

    @property
    def is_available(self) -> bool:
        """
        This renderer will only be available if this returns ``True``. You can use this to limit this renderer
        to certain events. Defaults to ``True``.
        """
        return True


class TemplateBasedMailRenderer(BaseHTMLMailRenderer):

    @property
    def template_name(self):
        raise NotImplementedError()

    def render(self, plain_body: str, plain_signature: str, subject: str, order: Order, position: OrderPosition) -> str:
        body_md = markdown_compile_email(plain_body)
        htmlctx = {
            'site': settings.PRETIX_INSTANCE_NAME,
            'site_url': settings.SITE_URL,
            'body': body_md,
            'subject': str(subject),
            'color': '#8E44B3'
        }
        if self.event:
            htmlctx['event'] = self.event
            htmlctx['color'] = self.event.settings.primary_color

        if plain_signature:
            signature_md = plain_signature.replace('\n', '<br>\n')
            signature_md = markdown_compile_email(signature_md)
            htmlctx['signature'] = signature_md

        if order:
            htmlctx['order'] = order

        if position:
            htmlctx['position'] = position

        tpl = get_template(self.template_name)
        body_html = inline_css(tpl.render(htmlctx))
        return body_html


class ClassicMailRenderer(TemplateBasedMailRenderer):
    verbose_name = _('pretix default')
    identifier = 'classic'
    thumbnail_filename = 'pretixbase/email/thumb.png'
    template_name = 'pretixbase/email/plainwrapper.html'


@receiver(register_html_mail_renderers, dispatch_uid="pretixbase_email_renderers")
def base_renderers(sender, **kwargs):
    return [ClassicMailRenderer]
