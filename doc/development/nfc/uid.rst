UID-based
=========

With UID-based NFC, only the unique ID (UID) of the NFC chip is used for identification purposes.
This can be used with virtually all NFC chips that provide compatibility with the NFC reader in use, typically at least all chips that comply with ISO/IEC 14443-3A.

We make only one restriction: The UID may not start with ``08``, since that usually signifies a randomized UID that changes on every read (which would not be very useful).

.. warning:: The UID-based approach provides only a very low level of security. It is easy to clone a chip with the same
             UID and impersonate someone else.