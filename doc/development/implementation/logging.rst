Logging and notifications
=========================

As pretix is handling monetary transactions, we are very careful to make it possible to review all changes
in the system that lead to the current state.

.. _`logging`:

Logging changes
---------------

We log data changes to the database in a format that makes it possible to display those logs to a human, if
required. pretix stores all those logs centrally in a model called :py:class:`pretix.base.models.LogEntry`.
We recommend all relevant models to inherit from ``LoggedModel`` as it simplifies creating new log entries:

.. autoclass:: pretix.base.models.LoggedModel
   :members: log_action, all_logentries

To actually log an action, you can just call the ``log_action`` method on your object:

.. code-block:: python

   order.log_action('pretix.event.order.comment', user=user,
                    data={"new_comment": "Hello, world."})

The positional ``action`` argument should represent the type of action and should be globally unique, we
recommend to prefix it with your package name, e.g. ``paypal.payment.rejected``. The ``user`` argument is
optional and may contain the user who performed the action. The optional ``data`` argument can contain
additional information about this action.

Logging form actions
""""""""""""""""""""

A very common use case is to log the changes to a model that have been done in a ``ModelForm``. In this case,
we generally use a custom ``form_valid`` method on our ``FormView`` that looks like this:

.. code-block:: python

    @transaction.atomic
    def form_valid(self, form):
        if form.has_changed():
            self.request.event.log_action('pretix.event.changed', user=self.request.user, data={
                k: getattr(self.request.event, k) for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

It gets a little bit more complicated if your form allows file uploads:

.. code-block:: python

    @transaction.atomic
    def form_valid(self, form):
        if form.has_changed():
            self.request.event.log_action(
                'pretix.event.changed', user=self.request.user, data={
                    k: (form.cleaned_data.get(k).name
                        if isinstance(form.cleaned_data.get(k), File)
                        else form.cleaned_data.get(k))
                    for k in form.changed_data
                }
            )
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)


Displaying logs
"""""""""""""""

If you want to display the logs of a particular object to a user in the backend, you can use the
following ready-to-include template::

   {% include "pretixcontrol/includes/logs.html" with obj=order %}

We now need a way to translate the action codes like ``pretix.event.changed`` into human-readable
strings. The :py:attr:`pretix.base.logentrytypes.log_entry_types` :ref:`registry <registries>` allows you to do so. A simple
implementation could look like:

.. code-block:: python

    from django.utils.translation import gettext as _
    from pretix.base.logentrytypes import log_entry_types


    @log_entry_types.new_from_dict({
        'pretix.event.order.comment': _('The order\'s internal comment has been updated to: {new_comment}'),
        'pretix.event.order.paid': _('The order has been marked as paid.'),
        # ...
    })
    class CoreOrderLogEntryType(OrderLogEntryType):
        pass

Please note that you always need to define your own inherited ``LogEntryType`` class in your plugin. If you would just
register an instance of a ``LogEntryType`` class defined in pretix core, it cannot be automatically detected as belonging
to your plugin, leading to confusing user interface situations.


Customizing log entry display
"""""""""""""""""""""""""""""

The base ``LogEntryType`` classes allow for varying degree of customization in their descendants.

If you want to add another log message for an existing core object (e.g. an :class:`Order <pretix.base.models.Order>`,
:class:`Item <pretix.base.models.Item>`, or :class:`Voucher <pretix.base.models.Voucher>`), you can inherit
from its predefined :class:`LogEntryType <pretix.base.logentrytypes.LogEntryType>`, e.g.
:class:`OrderLogEntryType <pretix.base.logentrytypes.OrderLogEntryType>`, and just specify a new plaintext string.
You can use format strings to insert information from the LogEntry's `data` object as shown in the section above.

If you define a new model object in your plugin, you should make sure proper object links in the user interface are
displayed for it. If your model object belongs logically to a pretix :class:`Event <pretix.base.models.Event>`, you can inherit from :class:`EventLogEntryType <pretix.base.logentrytypes.EventLogEntryType>`,
and set the ``object_link_*`` fields accordingly. ``object_link_viewname`` refers to a django url name, which needs to
accept the arguments `organizer` and `event`, containing the respective slugs, and additional arguments provided by
``object_link_args``. The default implementation of ``object_link_args`` will return an argument named by
````object_link_argname``, with a value of ``content_object.pk`` (the primary key of the model object).
If you want to customize the name displayed for the object (instead of the result of calling ``str()`` on it),
overwrite ``object_link_display_name``.


.. code-block:: python

    class ItemLogEntryType(EventLogEntryType):
        object_link_wrapper = _('Product {val}')

        # link will be generated as reverse('control:event.item', {'organizer': ..., 'event': ..., 'item': item.pk})
        object_link_viewname = 'control:event.item'
        object_link_argname = 'item'


.. code-block:: python

    class OrderLogEntryType(EventLogEntryType):
        object_link_wrapper = _('Order {val}')

        # link will be generated as reverse('control:event.order', {'organizer': ..., 'event': ..., 'code': order.code})
        object_link_viewname = 'control:event.order'

        def object_link_args(self, order):
            return {'code': order.code}

        def object_link_display_name(self, order):
            return order.code

To show more sophisticated message strings, e.g. varying the message depending on information from the :class:`LogEntry <pretix.base.models.log.LogEntry>`'s
`data` object, override the `display` method:

.. code-block:: python

    @log_entry_types.new()
    class PaypalEventLogEntryType(EventLogEntryType):
        action_type = 'pretix.plugins.paypal.event'

        def display(self, logentry):
            event_type = logentry.parsed_data.get('event_type')
            text = {
                'PAYMENT.SALE.COMPLETED': _('Payment completed.'),
                'PAYMENT.SALE.DENIED': _('Payment denied.'),
                # ...
            }.get(event_type, f"({event_type})")
            return _('PayPal reported an event: {}').format(text)

.. automethod:: pretix.base.logentrytypes.LogEntryType.display

If your new model object does not belong to an :class:`Event <pretix.base.models.Event>`, you need to inherit directly from ``LogEntryType`` instead
of ``EventLogEntryType``, providing your own implementation of ``get_object_link_info`` if object links should be
displayed.

.. autoclass:: pretix.base.logentrytypes.LogEntryType
   :members: get_object_link_info



Sending notifications
---------------------

If you think that the logged information might be important or urgent enough to send out a notification to interested
organizers. In this case, you should listen for the :py:attr:`pretix.base.signals.register_notification_types` signal
to register a notification type:

.. code-block:: python

    @receiver(register_notification_types)
    def register_my_notification_types(sender, **kwargs):
        return [MyNotificationType(sender)]

Note that this event is different than other events send out by pretix: ``sender`` may be an event or ``None``. The
latter case is required to let the user define global notification preferences for all events.

You also need to implement a custom class that specifies how notifications should be handled for your notification type.
You should subclass the base ``NotificationType`` class and implement all its members:

.. autoclass:: pretix.base.notifications.NotificationType
   :members: action_type, verbose_name, required_permission, build_notification

A simple implementation could look like this:

.. code-block:: python

    class MyNotificationType(NotificationType):
        required_permission = "can_view_orders"
        action_type = "pretix.event.order.paid"
        verbose_name = _("Order has been paid")

        def build_notification(self, logentry: LogEntry):
            order = logentry.content_object

            order_url = build_absolute_uri(
                'control:event.order',
                kwargs={
                    'organizer': logentry.event.organizer.slug,
                    'event': logentry.event.slug,
                    'code': order.code
                }
            )

            n = Notification(
                event=logentry.event,
                title=_('Order {code} has been marked as paid').format(code=order.code),
                url=order_url
            )
            n.add_attribute(_('Order code'), order.code)
            n.add_action(_('View order details'), order_url)
            return n

As you can see, the relevant code is in the ``build_notification`` method that is supposed to create a ``Notification``
method that has a title, description, URL, attributes, and actions. The full definition of ``Notification`` is the
following:

.. autoclass:: pretix.base.notifications.Notification
   :members: add_action, add_attribute


Logging technical information
-----------------------------

If you just want to log technical information to a log file on disk that does not need to be parsed
and displayed later, you can just use Python's ``logging`` module:

.. code-block:: python

   import logging

   logger = logging.getLogger(__name__)

   logger.info('Startup complete.')

This is also very useful to provide debugging information when an exception occurs:

.. code-block:: python

   try:
      foo()
   except:
      logger.exception('Error when calling foo()')  # Traceback will automatically be appended
      messages.error(request, _('An error occured.'))
