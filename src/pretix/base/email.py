import inspect
import logging
from datetime import timedelta
from decimal import Decimal
from smtplib import SMTPResponseException

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.timezone import now
from django.utils.translation import get_language, ugettext_lazy as _
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
            'color': '#8E44B3',
            'rtl': get_language() in settings.LANGUAGES_RTL
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
    verbose_name = _('Default')
    identifier = 'classic'
    thumbnail_filename = 'pretixbase/email/thumb.png'
    template_name = 'pretixbase/email/plainwrapper.html'


class UnembellishedMailRenderer(TemplateBasedMailRenderer):
    verbose_name = _('Simple with logo')
    identifier = 'simple_logo'
    thumbnail_filename = 'pretixbase/email/thumb_simple_logo.png'
    template_name = 'pretixbase/email/simple_logo.html'


@receiver(register_html_mail_renderers, dispatch_uid="pretixbase_email_renderers")
def base_renderers(sender, **kwargs):
    return [ClassicMailRenderer, UnembellishedMailRenderer]


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

    def render_sample(self, event):
        """
        This method is called to generate a text to be used in email previews.
        This may only depend on the event.
        """
        raise NotImplementedError()


class SimpleFunctionalMailTextPlaceholder(BaseMailTextPlaceholder):
    def __init__(self, identifier, args, func, sample):
        self._identifier = identifier
        self._args = args
        self._func = func
        self._sample = sample

    @property
    def identifier(self):
        return self._identifier

    @property
    def required_context(self):
        return self._args

    def render(self, context):
        return self._func(**{k: context[k] for k in self._args})

    def render_sample(self, event):
        if callable(self._sample):
            return self._sample(event)
        else:
            return self._sample


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
    from pretix.base.models import InvoiceAddress
    from pretix.multidomain.urlreverse import build_absolute_uri

    ph = [
        SimpleFunctionalMailTextPlaceholder(
            'event', ['event'], lambda event: event.name, lambda event: event.name
        ),
        SimpleFunctionalMailTextPlaceholder(
            'event_slug', ['event'], lambda event: event.slug, lambda event: event.slug
        ),
        SimpleFunctionalMailTextPlaceholder(
            'code', ['order'], lambda order: order.code, 'F8VVL'
        ),
        SimpleFunctionalMailTextPlaceholder(
            'total', ['order'], lambda order: LazyNumber(order.total), lambda event: LazyNumber(Decimal('42.23'))
        ),
        SimpleFunctionalMailTextPlaceholder(
            'currency', ['event'], lambda event: event.currency, lambda event: event.currency
        ),
        SimpleFunctionalMailTextPlaceholder(
            'total_with_currency', ['event', 'order'], lambda event, order: LazyCurrencyNumber(order.total,
                                                                                               event.currency),
            lambda event: LazyCurrencyNumber(Decimal('42.23'), event.currency)
        ),
        SimpleFunctionalMailTextPlaceholder(
            'expire_date', ['event', 'order'], lambda event, order: LazyDate(order.expires.astimezone(event.timezone)),
            lambda event: LazyDate(now() + timedelta(days=15))
            # TODO: This used to be "date" in some placeholders, add a migration!
        ),
        SimpleFunctionalMailTextPlaceholder(
            'url', ['order', 'event'], lambda order, event: build_absolute_uri(
                event,
                'presale:event.order.open', kwargs={
                    'order': order.code,
                    'secret': order.secret,
                    'hash': order.email_confirm_hash()
                }
            ), lambda event: build_absolute_uri(
                event,
                'presale:event.order.open', kwargs={
                    'order': 'F8VVL',
                    'secret': '6zzjnumtsx136ddy',
                    'hash': '98kusd8ofsj8dnkd'
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
            ),
            lambda event: build_absolute_uri(
                event,
                'presale:event.order.position', kwargs={
                    'order': 'F8VVL',
                    'secret': '6zzjnumtsx136ddy',
                    'position': '123'
                }
            ),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'url', ['waiting_list_entry', 'event'],
            lambda waiting_list_entry, event: build_absolute_uri(
                event, 'presale:event.redeem'
            ) + '?voucher=' + waiting_list_entry.voucher.code,
            lambda event: build_absolute_uri(
                event,
                'presale:event.redeem',
            ) + '?voucher=68CYU2H6ZTP3WLK5',
        ),
        SimpleFunctionalMailTextPlaceholder(
            'invoice_name', ['invoice_address'], lambda invoice_address: invoice_address.name or '',
            _('John Doe')
        ),
        SimpleFunctionalMailTextPlaceholder(
            'invoice_company', ['invoice_address'], lambda invoice_address: invoice_address.company or '',
            _('Sample Corporation')
        ),
        SimpleFunctionalMailTextPlaceholder(
            'orders', ['event', 'orders'], lambda event, orders: '\n' + '\n\n'.join(
                '* {} - {}'.format(
                    order.full_code,
                    build_absolute_uri(event, 'presale:event.order', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'order': order.code,
                        'secret': order.secret
                    }),
                )
                for order in orders
            ), lambda event: '\n' + '\n\n'.join(
                '* {} - {}'.format(
                    '{}-{}'.format(event.slug.upper(), order['code']),
                    build_absolute_uri(event, 'presale:event.order', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'order': order['code'],
                        'secret': order['secret']
                    }),
                )
                for order in [
                    {'code': 'F8VVL', 'secret': '6zzjnumtsx136ddy'},
                    {'code': 'HIDHK', 'secret': '98kusd8ofsj8dnkd'},
                    {'code': 'OPKSB', 'secret': '09pjdksflosk3njd'}
                ]
            ),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'hours', ['event', 'waiting_list_entry'], lambda event, waiting_list_entry:
            event.settings.waiting_list_hours,
            lambda event: event.settings.waiting_list_hours
        ),
        SimpleFunctionalMailTextPlaceholder(
            'product', ['waiting_list_entry'], lambda waiting_list_entry: waiting_list_entry.item.name,
            _('Sample Admission Ticket')
        ),
        SimpleFunctionalMailTextPlaceholder(
            'code', ['waiting_list_entry'], lambda waiting_list_entry: waiting_list_entry.voucher.code,
            '68CYU2H6ZTP3WLK5'
        ),
        SimpleFunctionalMailTextPlaceholder(
            'voucher_list', ['voucher_list'], lambda voucher_list: '\n'.join(voucher_list),
            '    68CYU2H6ZTP3WLK5\n    7MB94KKPVEPSMVF2'
        ),
        SimpleFunctionalMailTextPlaceholder(
            'url', ['event', 'voucher_list'], lambda event, voucher_list: build_absolute_uri(event, 'presale:event.index', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            }), lambda event: build_absolute_uri(event, 'presale:event.index', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            })
        ),
        SimpleFunctionalMailTextPlaceholder(
            'name', ['name'], lambda name: name,
            _('John Doe')
        ),
        SimpleFunctionalMailTextPlaceholder(
            'comment', ['comment'], lambda comment: comment,
            _('An individual text with a reason can be inserted here.'),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'payment_info', ['order', 'payment'], _placeholder_payment,
            _('The amount has been charged to your card.'),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'payment_info', ['payment_info'], lambda payment_info: payment_info,
            _('Please transfer money to this bank account: 9999-9999-9999-9999'),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'attendee_name', ['position'], lambda position: position.attendee_name,
            _('John Doe'),
        ),
        SimpleFunctionalMailTextPlaceholder(
            'name', ['position_or_address'],
            lambda position_or_address: (
                position_or_address.name
                if isinstance(position_or_address, InvoiceAddress)
                else position_or_address.attendee_name
            ),
            _('John Doe'),
        ),
    ]

    name_scheme = PERSON_NAME_SCHEMES[sender.settings.name_scheme]
    for f, l, w in name_scheme['fields']:
        if f == 'full_name':
            continue
        ph.append(SimpleFunctionalMailTextPlaceholder(
            'attendee_name_%s' % f, ['position'], lambda position, f=f: position.attendee_name_parts.get(f, ''),
            name_scheme['sample'][f]
        ))
        ph.append(SimpleFunctionalMailTextPlaceholder(
            'name_%s' % f, ['position_or_address'],
            lambda position_or_address, f=f: (
                position_or_address.name_parts.get(f, '')
                if isinstance(position_or_address, InvoiceAddress)
                else position_or_address.attendee_name_parts.get(f, '')
            ),
            name_scheme['sample'][f]
        ))

    for k, v in sender.meta_data.items():
        ph.append(SimpleFunctionalMailTextPlaceholder(
            'meta_%s' % k, ['event'], lambda event, k=k: event.meta_data[k],
            v
        ))

    return ph
