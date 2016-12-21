from collections import OrderedDict
from typing import Tuple

from django import forms
from django.http import HttpRequest
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, OrderPosition
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

    def generate(self, order: OrderPosition) -> Tuple[str, str, str]:
        """
        This method should generate the download file and return a tuple consisting of a
        filename, a file type and file content. The extension will be taken from the filename
        which is otherwise ignored.
        """
        raise NotImplementedError()

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
