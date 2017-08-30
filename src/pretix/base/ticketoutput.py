import os
import tempfile
from collections import OrderedDict
from typing import Tuple
from zipfile import ZipFile

from django import forms
from django.http import HttpRequest
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, Order, OrderPosition
from pretix.base.settings import SettingsSandbox


class BaseTicketOutput:
    """
    This is the base class for all ticket outputs.
    """

    def __init__(self, event: Event):
        self.event = event
        self.settings = SettingsSandbox('ticketoutput', self.identifier, event)

    def __str__(self):
        return self.identifier

    @property
    def is_enabled(self) -> bool:
        """
        Returns whether or whether not this output is enabled.
        By default, this is determined by the value of the ``_enabled`` setting.
        """
        return self.settings.get('_enabled', as_type=bool)

    @property
    def multi_download_enabled(self) -> bool:
        """
        Returns whether or not the ``generate_order`` method may be called. Returns
        ``True`` by default.
        """
        return True

    def generate(self, position: OrderPosition) -> Tuple[str, str, str]:
        """
        This method should generate the download file and return a tuple consisting of a
        filename, a file type and file content. The extension will be taken from the filename
        which is otherwise ignored.

        .. note:: If the event uses the event series feature (internally called subevents)
                  and your generated ticket contains information like the event name or date,
                  you probably want to display the properties of the subevent. A common pattern
                  to do this would be a declaration ``ev = position.subevent or position.order.event``
                  and then access properties that are present on both classes like ``ev.name`` or
                  ``ev.date_from``.
        """
        raise NotImplementedError()

    def generate_order(self, order: Order) -> Tuple[str, str, str]:
        """
        This method is the same as order() but should not generate one file per order position
        but instead one file for the full order.

        This method is optional to implement. If you don't implement it, the default
        implementation will offer a zip file of the generate() results for the order positions.

        This method should generate a download file and return a tuple consisting of a
        filename, a file type and file content. The extension will be taken from the filename
        which is otherwise ignored.

        If you override this method, make sure that positions that are addons (i.e. ``addon_to``
        is set) are only outputted if the event setting ``ticket_download_addons`` is active.
        Do the same for positions that are non-admission without ``ticket_download_nonadm`` active.
        """
        with tempfile.TemporaryDirectory() as d:
            with ZipFile(os.path.join(d, 'tmp.zip'), 'w') as zipf:
                for pos in order.positions.all():
                    if pos.addon_to_id and not self.event.settings.ticket_download_addons:
                        continue
                    if not pos.item.admission and not self.event.settings.ticket_download_nonadm:
                        continue
                    fname, __, content = self.generate(pos)
                    zipf.writestr('{}-{}{}'.format(
                        order.code, pos.positionid, os.path.splitext(fname)[1]
                    ), content)

            with open(os.path.join(d, 'tmp.zip'), 'rb') as zipf:
                return '{}-{}.zip'.format(order.code, self.identifier), 'application/zip', zipf.read()

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this ticket output. This should be short but
        self-explanatory. Good examples include 'PDF tickets' and 'Passbook'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this ticket output.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def settings_form_fields(self) -> dict:
        """
        When the event's administrator visits the event configuration
        page, this method is called to return the configuration fields available.

        It should therefore return a dictionary where the keys should be (unprefixed)
        settings keys and the values should be corresponding Django form fields.

        The default implementation returns the appropriate fields for the ``_enabled``
        setting mentioned above.

        We suggest that you return an ``OrderedDict`` object instead of a dictionary
        and make use of the default implementation. Your implementation could look
        like this::

            @property
            def settings_form_fields(self):
                return OrderedDict(
                    list(super().settings_form_fields.items()) + [
                        ('paper_size',
                         forms.CharField(
                             label=_('Paper size'),
                             required=False
                         ))
                    ]
                )

        .. WARNING:: It is highly discouraged to alter the ``_enabled`` field of the default
                     implementation.
        """
        return OrderedDict([
            ('_enabled',
             forms.BooleanField(
                 label=_('Enable output'),
                 required=False,
             )),
        ])

    def settings_content_render(self, request: HttpRequest) -> str:
        """
        When the event's administrator visits the event configuration
        page, this method is called. It may return HTML containing additional information
        that is displayed below the form fields configured in ``settings_form_fields``.
        """
        pass

    @property
    def download_button_text(self) -> str:
        """
        The text on the download button in the frontend.
        """
        return _('Download ticket')
