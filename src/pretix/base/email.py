#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import logging
from itertools import groupby
from smtplib import SMTPResponseException
from typing import TypeVar

import bleach
import css_inline
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.db.models import Count
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import get_language, gettext_lazy as _

from pretix.base.models import Event
from pretix.base.signals import register_html_mail_renderers
from pretix.base.templatetags.rich_text import (
    DEFAULT_CALLBACKS, EMAIL_RE, URL_RE, abslink_callback,
    markdown_compile_email, truelink_callback,
)
from pretix.helpers.format import FormattedString, SafeFormatter, format_map

from pretix.base.services.placeholders import (  # noqa
    get_available_placeholders, PlaceholderContext
)
from pretix.base.services.placeholders import ( # noqa
    BaseTextPlaceholder as BaseMailTextPlaceholder,
    SimpleFunctionalTextPlaceholder as SimpleFunctionalMailTextPlaceholder,
)
from pretix.base.settings import get_name_parts_localized # noqa

logger = logging.getLogger('pretix.base.email')

T = TypeVar("T", bound=EmailBackend)


def test_custom_smtp_backend(backend: T, from_addr: str) -> None:
    try:
        backend.open()
        backend.connection.ehlo_or_helo_if_needed()
        (code, resp) = backend.connection.mail(from_addr, [])
        if code != 250:
            logger.warning('Error testing mail settings, code %d, resp: %s' % (code, resp))
            raise SMTPResponseException(code, resp)
        (code, resp) = backend.connection.rcpt('testdummy@pretix.eu')
        if (code != 250) and (code != 251):
            logger.warning('Error testing mail settings, code %d, resp: %s' % (code, resp))
            raise SMTPResponseException(code, resp)
    finally:
        backend.close()


class BaseHTMLMailRenderer:
    """
    This is the base class for all HTML email renderers.
    """

    def __init__(self, event: Event, organizer=None):
        self.event = event
        self.organizer = organizer

    def __str__(self):
        return self.identifier

    def render(self, plain_body: str, plain_signature: str, subject: str, order=None,
               position=None, context=None) -> str:
        """
        This method should generate the HTML part of the email.

        :param plain_body: The body of the email in plain text.
        :param plain_signature: The signature with event organizer contact details in plain text.
        :param subject: The email subject.
        :param order: The order if this email is connected to one, otherwise ``None``.
        :param position: The order position if this email is connected to one, otherwise ``None``.
        :param context: Context to use to render placeholders in the plain body
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

    def compile_markdown(self, plaintext, context=None):
        return markdown_compile_email(plaintext, context=context)

    def render(self, plain_body: str, plain_signature: str, subject: str, order, position, context) -> str:
        apply_format_map = not isinstance(plain_body, FormattedString)
        body_md = self.compile_markdown(plain_body, context)
        if context:
            linker = bleach.Linker(
                url_re=URL_RE,
                email_re=EMAIL_RE,
                callbacks=DEFAULT_CALLBACKS + [truelink_callback, abslink_callback],
                parse_email=True
            )
            if apply_format_map:
                body_md = format_map(
                    body_md,
                    context=context,
                    mode=SafeFormatter.MODE_RICH_TO_HTML,
                    linkifier=linker
                )
        htmlctx = {
            'site': settings.PRETIX_INSTANCE_NAME,
            'site_url': settings.SITE_URL,
            'body': body_md,
            'subject': str(subject),
            'color': settings.PRETIX_PRIMARY_COLOR,
            'rtl': get_language() in settings.LANGUAGES_RTL or get_language().split('-')[0] in settings.LANGUAGES_RTL,
        }
        if self.organizer:
            htmlctx['organizer'] = self.organizer
            htmlctx['color'] = self.organizer.settings.primary_color

        if self.event:
            htmlctx['event'] = self.event
            htmlctx['color'] = self.event.settings.primary_color

        if plain_signature:
            signature_md = plain_signature.replace('\n', '<br>\n')
            signature_md = self.compile_markdown(signature_md)
            htmlctx['signature'] = signature_md

        if order:
            htmlctx['order'] = order
            positions = list(order.positions.select_related(
                'item', 'variation', 'subevent', 'addon_to'
            ).annotate(
                has_addons=Count('addons')
            ))
            htmlctx['cart'] = [(k, list(v)) for k, v in groupby(
                sorted(
                    positions,
                    key=lambda op: (
                        (op.addon_to.positionid if op.addon_to_id else op.positionid),
                        op.positionid
                    )
                ),
                key=lambda op: (
                    op.item,
                    op.variation,
                    op.subevent,
                    op.attendee_name,
                    op.addon_to_id,
                    (op.pk if op.has_addons else None)
                )
            )]

        if position:
            htmlctx['position'] = position
            htmlctx['ev'] = position.subevent or self.event

        tpl = get_template(self.template_name)
        body_html = tpl.render(htmlctx)

        inliner = css_inline.CSSInliner(keep_style_tags=False)
        body_html = inliner.inline(body_html)

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


def get_email_context(**kwargs):
    return PlaceholderContext(**kwargs).render_all()
