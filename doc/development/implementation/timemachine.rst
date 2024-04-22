Time machine mode
=================

In test mode, pretix provides a "time machine" feature which allows event organizers
to test their shop as if it were a different date and time. To enable this feature, they can
click on the clock icon in the test mode warning box.

Internally, this time machine mode is implemented by calling our custom :py:meth:`time_machine_now()`
function instead of :py:meth:`django.utils.timezone.now()` in all places where the fake time should be
taken into account. If you add code that uses the current date and time for checking whether some
product can be bought, you should use :py:meth:`time_machine_now`.

.. autofunction:: pretix.base.timemachine.time_machine_now

Background tasks
----------------

The time machine datetime is passed through the request flow via a thread-local variable (ContextVar).
Therefore, if you call a background task in the order process, where time_machine_now should be
respected, you need to pass it through manually as shown in the example below:

.. code-block:: python

    @app.task()
    def my_task(self, override_now_dt: datetime=None) -> None:
        with time_machine_now_assigned(override_now_dt):
            # ...do something that uses time_machine_now()

    my_task.apply_async(kwargs={'override_now_dt': time_machine_now(default=None)})


.. autofunction:: pretix.base.timemachine.time_machine_now_assigned
