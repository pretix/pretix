.. highlight:: python
   :linenothreshold: 5

.. _`importcol`:

Extending the order import process
==================================

It's possible through the backend to import orders into pretix, for example from a legacy ticketing system. If your
plugins defines additional data structures around orders, it might be useful to make it possible to import them as well.

Import process
--------------

Here's a short description of pretix' import process to show you where the system will need to interact with your plugin.
You can find more detailed descriptions of the attributes and methods further below.

1. The user uploads a CSV file. The system tries to parse the CSV file and understand its column headers.

2. A preview of the file is shown to the user and the user is asked to assign the various different input parameters to
   columns of the file or static values. For example, the user either needs to manually select a product or specify a
   column that contains a product. For this purpose, a select field is rendered for every possible input column,
   allowing the user to choose between a default/empty value (defined by your ``default_value``/``default_label``)
   attributes, the columns of the uploaded file, or a static value (defined by your ``static_choices`` method).

3. The user submits its assignment and the system uses the ``resolve`` method of all columns to get the raw value for
   all columns.

4. The system uses the ``clean`` method of all columns to verify that all input fields are valid and transformed to the
   correct data type.

5. The system prepares internal model objects (``Order`` etc) and uses the ``assign`` method of all columns to assign
   these objects with actual values.

6. The system saves all of these model objects to the database in a database transaction. Plugins can create additional
   objects in this stage through their ``save`` method.

Column registration
-------------------

The import API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available import columns. Your plugin
should listen for this signal and return the subclass of ``pretix.base.orderimport.ImportColumn``
that we'll provide in this plugin:

.. sourcecode:: python

    from django.dispatch import receiver

    from pretix.base.signals import order_import_columns


    @receiver(order_import_columns, dispatch_uid="custom_columns")
    def register_column(sender, **kwargs):
        return [
            EmailColumn(sender),
        ]

The column class API
--------------------

.. class:: pretix.base.orderimport.ImportColumn

   The central object of each import extension is the subclass of ``ImportColumn``.

   .. py:attribute:: ImportColumn.event

      The default constructor sets this property to the event we are currently
      working for.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: default_value

   .. autoattribute:: default_label

   .. autoattribute:: initial

   .. automethod:: static_choices

   .. automethod:: resolve

   .. automethod:: clean

   .. automethod:: assign

   .. automethod:: save

Example
-------

For example, the import column responsible for assigning email addresses looks like this:

.. sourcecode:: python

   class EmailColumn(ImportColumn):
       identifier = 'email'
       verbose_name = _('E-mail address')

       def clean(self, value, previous_values):
           if value:
               EmailValidator()(value)
           return value

       def assign(self, value, order, position, invoice_address, **kwargs):
           order.email = value
