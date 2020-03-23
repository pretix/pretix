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

To actually log an action, you can just call the ``log_action`` method on your object::

   order.log_action('pretix.event.order.canceled', user=user, data={})

The positional ``action`` argument should represent the type of action and should be globally unique, we
recommend to prefix it with your package name, e.g. ``paypal.payment.rejected``. The ``user`` argument is
optional and may contain the user who performed the action. The optional ``data`` argument can contain
additional information about this action.

Logging form actions
""""""""""""""""""""

A very common use case is to log the changes to a model that have been done in a ``ModelForm``. In this case,
we generally use a custom ``form_valid`` method on our ``FormView`` that looks like this::

    @transaction.atomic
    def form_valid(self, form):
        if form.has_changed():
            self.request.event.log_action('pretix.event.changed', user=self.request.user, data={
                k: getattr(self.request.event, k) for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

It gets a little bit more complicated if your form allows file uploads::

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
strings. The :py:attr:`pretix.base.signals.logentry_display` signals allows you to do so. A simple
implementation could look like::

    from django.utils.translation import gettext as _
    from pretix.base.signals import logentry_display

    @receiver(signal=logentry_display)
    def pretixcontrol_logentry_display(sender, logentry, **kwargs):
        plains = {
            'pretix.event.order.paid': _('The order has been marked as paid.'),
            'pretix.event.order.refunded': _('The order has been refunded.'),
            'pretix.event.order.canceled': _('The order has been canceled.'),
            ...
        }
        if logentry.action_type in plains:
            return plains[logentry.action_type]

Sending notifications
---------------------

If you think that the logged information might be important or urgent enough to send out a notification to interested
organizers. In this case, you should listen for the :py:attr:`pretix.base.signals.register_notification_types` signal
to register a notification type::

    @receiver(register_notification_types)
    def register_my_notification_types(sender, **kwargs):
        return [MyNotificationType(sender)]

Note that this event is different than other events send out by pretix: ``sender`` may be an event or ``None``. The
latter case is required to let the user define global notification preferences for all events.

You also need to implement a custom class that specifies how notifications should be handled for your notification type.
You should subclass the base ``NotificationType`` class and implement all its members:

.. autoclass:: pretix.base.notifications.NotificationType
   :members: action_type, verbose_name, required_permission, build_notification

A simple implementation could look like this::

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
and displayed later, you can just use Python's ``logging`` module::

   import logging

   logger = logging.getLogger(__name__)

   logger.info('Startup complete.')

This is also very useful to provide debugging information when an exception occurs::

   try:
      foo()
   except:
      logger.exception('Error when calling foo()')  # Traceback will automatically be appended
      messages.error(request, _('An error occured.'))
