Ticket secret generators
========================

pretix allows you to change the way in which ticket secrets (also known as "ticket codes", "barcodes", …)
are generated. This affects the value of the QR code in any tickets issued by pretix, regardless of ticket
format.

.. note:: This is intended for highly advanced use cases, usually when huge numbers of tickets (> 25k per event)
          are involved. **If you don't know whether you need this, you probably don't.**

Default: Random secrets
-----------------------

By default, pretix generates a random code for every ticket, consisting of 32 lower case characters and
numbers. The characters ``oO1il`` are avoided to reduce confusion when ticket codes are printed and need to
be typed in manually.

Choosing random codes has a number of advantages:

* Ticket codes are short, which makes QR codes easier to scan. At the same time, it is absolutely impossible to
  guess or forge a valid ticket code.

* The code does not need to change if the ticket changes. For example, if an attendee is re-booked to a
  different product or date, they can keep their ticket and it is just mapped to the new product in the
  database.

This approach works really well for 99 % or events running with pretix.
The big caveat is that the scanner needs to access a database of all ticket codes in order to know whether a ticket
code is valid and what kind of ticket it represents.

When scanning online this is no problem at all, since the pretix server always has such a database. In case your local
internet connection is interrupted or the pretix server goes down, though, there needs to be a database locally on the
scanner.

Therefore, our pretixSCAN apps by default download the database of all valid tickets onto the device itself. This makes
it possible to seamlessly switch into offline mode when the connection is lost and continue scanning with the maximum
possible feature set.

There are a few situations in which this approach is not ideal:

* When running a single event with 25k or more valid tickets, downloading all ticket data onto the scanner may just
  take too much time and resources.

* When the risk of losing sensible data by losing one of the scanner devices is not acceptable.

* When offline mode needs to be used regularly and newly-purchased tickets need to be valid immediately after purchase,
  without being able to tolerate a few minutes of delay.

Signature schemes
-----------------

The alternative approach that is included with pretix is to choose a signature-based ticket code generation scheme.
These secrets include the most important information that is required for verifying their validity and use modern
cryptography to make sure they cannot be forged.

Currently, pretix ships with one such scheme ("pretix signature scheme 1") which encodes the product, the product
variation, and the date (if inside an event series) into the ticket code and signs the code with a `EdDSA`_ signature.
This allows to verify whether a ticket is allowed to enter without any database or connection to the server, but has
a few important drawbacks:

* Whenever the product, variation or date of a ticket changes or the ticket is canceled, the ticket code needs to be
  changed and the old code needs to be put on a revocation list. This revocation list again needs to be downloaded by
  all scanning devices (but is usually much smaller than the ticket database). The main downside is that the attendee
  needs to download their new ticket and can no longer use the old one.

* Scanning in offline mode is much more limited, since the scanner has no information about previous usages of the
  ticket, attendee names, seating information, etc.

Comparison of scanning behaviour
--------------------------------

=============================================== =================================== =================================== =================================== ================================= =====================================
Scan mode                                       Online                                                                  Offline
----------------------------------------------- ----------------------------------- -----------------------------------------------------------------------------------------------------------------------------------------------
Synchronization setting                         any                                 Synchronize orders                                                      Don't synchronize orders
----------------------------------------------- ----------------------------------- ----------------------------------------------------------------------- -----------------------------------------------------------------------
Ticket secrets                                  any                                 Random                              Signed                              Random                            Signed
=============================================== =================================== =================================== =================================== ================================= =====================================
Scenario supported on platforms                 Android, Desktop, iOS               Android, Desktop, iOS               Android, Desktop                    Android, Desktop                  Android, Desktop
Synchronization speed for large data sets                                           slow                                slow                                fast                              fast
Tickets can be scanned                          yes                                 yes                                 yes                                 no                                yes
Ticket is valid after sale                      immediately                         next sync (~5 minutes)              immediately                         never                             immediately
Same ticket can be scanned multiple times       no                                  yes, before data is synced          yes, before data is synced          n/a                               yes, always
Custom check-in rules                           yes                                 yes                                 yes (limited directly after sale)   n/a                               yes, but only based on product,
                                                                                                                                                                                              variation and date, not on previous
                                                                                                                                                                                              scans
Name and seat visible on scanner                yes                                 yes                                 yes (except directly after sale)    n/a                               no
Order-specific check-in attention flag          yes                                 yes                                 yes (except directly after sale)    n/a                               no
Ticket search by order code or name             yes                                 yes                                 yes (except directly after sale)    no                                no
Check-in statistics on scanner                  yes                                 yes                                 mostly accurate                     no                                no
=============================================== =================================== =================================== =================================== ================================= =====================================

.. _EdDSA: https://en.wikipedia.org/wiki/EdDSA#Ed25519
