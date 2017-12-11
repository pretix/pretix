from typing import Tuple


class BaseExporter:
    """
    This is the base class for all data exporters
    """

    def __init__(self, event):
        self.event = event

    def __str__(self):
        return self.identifier

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this exporter. This should be short but
        self-explaining. Good examples include 'JSON' or 'Microsoft Excel'.
        """
        raise NotImplementedError()  # NOQA

    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this exporter.
        This should only contain lowercase letters and in most
        cases will be the same as your package name.
        """
        raise NotImplementedError()  # NOQA

    @property
    def export_form_fields(self) -> dict:
        """
        When the event's administrator visits the export page, this method
        is called to return the configuration fields available.

        It should therefore return a dictionary where the keys should be field names and
        the values should be corresponding Django form fields.

        We suggest that you return an ``OrderedDict`` object instead of a dictionary.
        Your implementation could look like this::

            @property
            def export_form_fields(self):
                return OrderedDict(
                    [
                        ('tab_width',
                         forms.IntegerField(
                             label=_('Tab width'),
                             default=4
                         ))
                    ]
                )
        """
        return {}

    def render(self, form_data: dict) -> Tuple[str, str, str]:
        """
        Render the exported file and return a tuple consisting of a filename, a file type
        and file content.

        :type form_data: dict
        :param form_data: The form data of the export details form

        Note: If you use a ``ModelChoiceField`` (or a ``ModelMultipleChoiceField``), the
        ``form_data`` will not contain the model instance but only it's primary key (or
        a list of primary keys) for reasons of internal serialization when using background
        tasks.
        """
        raise NotImplementedError()  # NOQA
