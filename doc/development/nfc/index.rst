NFC media
=========

pretix supports using NFC chips as "reusable media", for example to store gift cards or tickets.

Most of this implementation currently lives in our proprietary app pretixPOS, but in the future might also become part of our open-source pretixSCAN solution.
Either way, we want this to be an open ecosystem and therefore document the exact mechanisms in use on the following pages.

We support multiple implementations of NFC media, each documented on its own page:

.. toctree::
   :maxdepth: 2

   uid
   mf0aes
