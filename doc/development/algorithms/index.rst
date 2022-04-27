Algorithms
==========

The business logic inside pretix is full of complex algorithms making decisions based on all the hundreds of settings
and input parameters available. Some of them are documented here as graphs, either because fully understanding them is very important
when working on features close to them, or because they also need to be re-implemented by client-side components like our
ticket scanning apps and we want to ensure the implementations are as similar as possible to avoid confusion.

.. toctree::
   :maxdepth: 2

   pricing
   checkin
   layouts
