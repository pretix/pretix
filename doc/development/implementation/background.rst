Background tasks
================

pretix provides the ability to run all longer-running tasks like generating ticket files or sending emails
in a background thread instead of the webserver process. We use the well-established `Celery`_ project to
implement this. However, as celery requires running a task queue like RabbitMQ and a result storage such as
Redis to work efficiently, we don't like to *depend* on celery being available to make small-scale installations
of pretix more straightforward. For this reason, the "background" in "background task" is always optional.

The Django settings variable ``settings.HAS_CELERY`` provides information on whether celery is configured
in the current installation.

Implementing a task
-------------------

A common pattern for implementing "optionally-asynchronous" tasks that can be seen a lot in ``pretix.base.services``
looks like this::

    def my_task(argument1, argument2):
        # Important: All arguments and return values need to be serializable into JSON.
        # Do not use model instances, use their primary keys instead!
        pass  # do your work here


    if settings.HAS_CELERY:
        # Transform this into a background task
        from pretix.celery import app  # Important: Do not import this unconditionally!

        my_task_async = app.task(export)

        def my_task(*args, **kwargs):
            my_task_async.apply_async(args=args, kwargs=kwargs)

This explicit declaration method also allows you to place some custom retry logic etc. in the asynchronous version.

Tasks in the request-response flow
----------------------------------

If your user needs to wait for the response of the asynchronous task, there are helpers available in ``pretix.presale``
that will probably move to ``pretix.base`` at some point. They consist of the view mixin ``AsyncAction`` that allows
you to easily write a view that kicks off and waits for an asynchronous task. ``AsyncAction`` will determine whether
to run the task asynchronously or not and will do some magic to look nice for users with and without JavaScript support.
A usage example taken directly from the code is::

    class OrderCancelDo(EventViewMixin, OrderDetailMixin, AsyncAction, View):
        """
        A view that executes a task asynchronously. A POST request will kick of the
        task into the background or run it in the foreground, if celery is not installed.
        In the former case, subsequent GET calls can be used to determinine the current
        status of the task.
        """

        task = cancel_order  # The task to be used, defined like above

        def get_success_url(self, value):
            """
            Returns the URL the user will be redirected to if the task succeeded.
            """
            return self.get_order_url()

        def get_error_url(self):
            """
            Returns the URL the user will be redirected to if the task failed.
            """
            return self.get_order_url()

        def post(self, request, *args, **kwargs):
            """
            Will be called while handling a POST request. This should process the
            request arguments in some way and call ``self.do`` with the task arguments
            to kick of the task.
            """
            if not self.order:
                raise Http404(_('Unknown order code or not authorized to access this order.'))
            return self.do(self.order.pk)

        def get_error_message(self, exception):
            """
            Returns the message that will be shown to the user if the task has failed.
            """
            if isinstance(exception, dict) and exception['exc_type'] == 'OrderError':
                return gettext(exception['exc_message'])
            elif isinstance(exception, OrderError):
                return str(exception)
            return super().get_error_message(exception)

On the client side, this can be used by simply adding a ``data-asynctask`` attribute to an HTML form. This will enable
AJAX sending of the form and display a loading indicator::

    <form method="post" data-asynctask
          action="{% eventurl request.event "presale:event.order.cancel.do" … %}">
        {% csrf_token %}
        ...
    </form>

.. _Celery: http://www.celeryproject.org/