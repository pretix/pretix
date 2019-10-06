import inspect
import logging
from smtplib import SMTPResponseException

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from inlinestyler.utils import inline_css

from pretix.base.i18n import LazyCurrencyNumber, LazyDate, LazyNumber
from pretix.base.models import Event
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import (
    register_html_mail_renderers, register_mail_placeholders,
)
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

    def render(self, plain_body: str, plain_signature: str, subject: str, order=None,
               position=None) -> str:
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

    def render(self, plain_body: str, plain_signature: str, subject: str, order, position) -> str:
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


class BaseMailTextPlaceholder:
    """
    This is the base class for for all email text placeholders.
    """

    @property
    def required_context(self):
        """
        This property should return a list of all attribute names that need to be
        contained in the base context so that this placeholder is available. By default,
        it returns a list containing the string "event".
        """
        return ["event"]

    @property
    def identifier(self):
        """
        This should return the identifier of this placeholder in the email.
        """
        raise NotImplementedError()

    def render(self, context):
        """
        This method is called to generate the actual text that is being
        used in the email. You will be passed a context dictionary with the
        base context attributes specified in ``required_context``. You are
        expected to return a plain-text string.
        """
        raise NotImplementedError()


class SimpleFunctionalMailTextPlaceholder(BaseMailTextPlaceholder):
    def __init__(self, identifier, args, func):
        self._identifier = identifier
        self._args = args
        self._func = func

    @property
    def identifier(self):
        return self._identifier

    @property
    def required_context(self):
        return self._args

    def render(self, context):
        return self._func(**{k: context[k] for k in self._args})


def get_available_placeholders(event, base_parameters):
    if 'order' in base_parameters:
        base_parameters.append('invoice_address')
    params = {}
    for r, val in register_mail_placeholders.send(sender=event):
        if not isinstance(val, (list, tuple)):
            val = [val]
        for v in val:
            if all(rp in base_parameters for rp in v.required_context):
                params[v.identifier] = v
    return params


def get_email_context(**kwargs):
    from pretix.base.models import InvoiceAddress

    event = kwargs['event']
    if 'order' in kwargs:
        try:
            kwargs['invoice_address'] = kwargs['order'].invoice_address
        except InvoiceAddress.DoesNotExist:
            kwargs['invoice_address'] = InvoiceAddress()
    ctx = {}
    for r, val in register_mail_placeholders.send(sender=event):
        if not isinstance(val, (list, tuple)):
            val = [val]
        for v in val:
            if all(rp in kwargs for rp in v.required_context):
                ctx[v.identifier] = v.render(kwargs)
    return ctx


def _placeholder_payment(order, payment):
    if not payment:
        return None
    if 'payment' in inspect.signature(payment.payment_provider.order_pending_mail_render).parameters:
        return str(payment.payment_provider.order_pending_mail_render(order, payment))
    else:
        return str(payment.payment_provider.order_pending_mail_render(order))


@receiver(register_mail_placeholders, dispatch_uid="pretixbase_register_mail_placeholders")
def base_placeholders(sender, **kwargs):
    from pretix.multidomain.urlreverse import build_absolute_uri

    ph = [
        SimpleFunctionalMailTextPlaceholder(
            'event', ['event'], lambda event: event.name,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'total', ['order'], lambda order: LazyNumber(order.total),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'currency', ['event'], lambda event: event.currency,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'total_with_currency', ['event', 'order'], lambda event, order: LazyCurrencyNumber(order.total, event.currency),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'expire_date', ['event', 'order'], lambda event, order: LazyDate(order.expires.astimezone(event.timezone)),
            # TODO: This used to be "date" in some placeholders, add a migration!
        ),
        SimpleFunctionalMailTextPlaceholder(
            'url', ['order', 'event'], lambda order, event: build_absolute_uri(
                order.event,
                'presale:event.order.open', kwargs={
                    'order': order.code,
                    'secret': order.secret,
                    'hash': order.email_confirm_hash()
                }
            ),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'url', ['event', 'position'], lambda event, position: build_absolute_uri(
                event,
                'presale:event.order.position',
                kwargs={
                    'order': position.order.code,
                    'secret': position.web_secret,
                    'position': position.positionid
                }
            )
        ),
        SimpleFunctionalMailTextPlaceholder(
            'url', ['waiting_list_entry', 'event'],
            lambda waiting_list_entry, event: build_absolute_uri(
                event, 'presale:event.redeem'
            ) + '?voucher=' + waiting_list_entry.voucher.code,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'invoice_name', ['invoice_address'], lambda invoice_address: invoice_address.name or ''
        ),
        SimpleFunctionalMailTextPlaceholder(
            'invoice_company', ['invoice_address'], lambda invoice_address: invoice_address.company or ''
        ),
        SimpleFunctionalMailTextPlaceholder(
            'orders', ['event', 'orders'], lambda event, orders: '\n'.join(
                ' - {} - {}'.format(
                    order.full_code,
                    build_absolute_uri('presale:event.order', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'order': order.code,
                        'secret': order.secret
                    }),
                )
                for order in orders
            )
        ),
        SimpleFunctionalMailTextPlaceholder(
            'hours', ['event', 'waiting_list_entry'], lambda event, waiting_list_entry: event.settings.waiting_list_hours,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'product', ['waiting_list_entry'], lambda waiting_list_entry: waiting_list_entry.item.name,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'code', ['waiting_list_entry'], lambda waiting_list_entry: waiting_list_entry.voucher.code,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'comment', ['comment'], lambda comment: comment,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'payment_info', ['order', 'payment'], _placeholder_payment,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'payment_info', ['payment_info'], lambda payment_info: payment_info,
        ),
        SimpleFunctionalMailTextPlaceholder(
            'attendee_name', ['position'], lambda position: position.attendee_name,
        ),
    ]

    name_scheme = PERSON_NAME_SCHEMES[sender.settings.name_scheme]
    for f, l, w in name_scheme['fields']:
        if f == 'full_name':
            continue
        ph.append(SimpleFunctionalMailTextPlaceholder(
            'attendee_name_%s' % f, ['position'], lambda position, f=f: position.attendee_name_parts.get(f, '')
        ))

    for k, v in sender.meta_data.items():
        ph.append(SimpleFunctionalMailTextPlaceholder(
            'meta_%s' % k, ['event'], lambda event, k=k: event.meta_data[k]
        ))

    return ph
