Mifare Ultralight AES
=====================

We offer an implementation that provides a higher security level than the UID-based approach and uses the `Mifare Ultralight AES`_ chip sold by NXP.
We believe the security model of this approach is adequate to the situation where this will usually be used and we'll outline known risks below.

If you want to dive deeper into the properties of the Mifare Ultralight AES chip, we recommend reading the `data sheet`_.

Random UIDs
-----------

Mifare Ultralight AES supports a feature that returns a randomized UID every time a non-authenticated user tries to
read the UID. This has a strong privacy benefit, since no unauthorized entity can use the NFC chips to track users.
On the other hand, this reduces interoperability of the system. For example, this prevents you from using the same NFC
chips for a different purpose where you only need the UID. This will also prevent your guests from reading their UID
themselves with their phones, which might be useful e.g. in debugging situations.

Since there's no one-size-fits-all choice here, you can enable or disable this feature in the pretix organizer
settings. If you change it, the change will apply to all newly encoded chips after the change.

Key management
--------------

For every organizer, the server will generate create a "key set", which consists of a publicly known ID (random 32-bit integer) and two 16-byte keys ("diversification key" and "UID key").

Using our :ref:`Device authentication mechanism <rest-deviceauth>`, an authorized device can submit a locally generated RSA public key to the server.
This key can no longer changed on the server once it is set, thus protecting against the attack scenario of a leaked device API token.

The server will then include key sets in the response to ``/api/v1/device/info``, encrypted with the device's RSA key.
This includes all key sets generated for the organizer the device belongs to, as well as all keys of organizers that have granted sufficient access to this organizer.

The device will decrypt the key sets using its RSA key and store the key sets locally.

.. warning:: The device **will** have access to the raw key sets. Therefore, there is a risk of leaked master keys if an
             authorized device is stolen or abused. Our implementation in pretixPOS attempts to make this very hard on
             modern, non-rooted Android devices by keeping them encrypted with the RSA key and only storing the RSA key
             in the hardware-backed keystore of the device. A sufficiently motivated attacker, however, will likely still
             be able to extract the keys from a stolen device.

Encoding a chip
---------------

When a new chip is encoded, the following steps will be taken:

- The UID of the chip is retrieved.

- A chip-specific key is generated using the mechanism documented in `AN10922`_ using the "diversification key" from the
  organizer's key set as the CMAC key and the diversification input concatenated in the from of ``0x01 + UID + APPID + SYSTEMID``
  with the following values:

  - The UID of the chip as ``UID``

  - ``"eu.pretix"`` (``0x65 0x75 0x2e 0x70 0x72 0x65 0x74 0x69 0x78``) as ``APPID``

  - The ``public_id`` from the organizer's key set as a 4-byte big-endian value as ``SYSTEMID``

- The chip-specific key is written to the chip as the "data protection key" (config pages 0x30 to 0x33)

- The UID key from the organizer's key set is written to the chip as the "UID retrieval key" (config pages 0x34 to 0x37)

- The config page 0x29 is set like this:

  - ``RID_ACT`` (random UID) to ``1`` or ``0`` based on the organizer's configuration
  - ``SEC_MSG_ACT`` (secure messaging) to ``1``
  - ``AUTH0`` (first page that needs authentication) to 0x04 (first non-UID page)

- The config page 0x2A is set like this:

  - ``PROT`` to ``0`` (only write access restricted, not read access)
  - ``AUTHLIM`` to ``256`` (maximum number of wrong authentications before "self-desctruction")
  - Everything else to its default value (no lock bits are set)

- The ``public_id`` of the key set will be written to page 0x04 as a big-endian value

- The UID of the chip will be registered as a reusable medium on the server.

.. warning:: During encoding, the chip-specific key and the UID key are transmitted in plain text over the air. The
             security model therefore relies on the encoding of chips being performed in a trusted physical environment
             to prevent a nearby attacker from sniffing the keys with a strong antenna.

.. note:: If an attacker tries to authenticate with the chip 256 times using the wrong key, the chip will become
          unusable. A chip may also become unusable if it is detached from the reader in the middle of the encoding
          process (even though we've tried to implement it in a way that makes this unlikely).

Usage
-----

When a chip is presented to the NFC reader, the following steps will be taken:

- Command ``GET_VERSION`` is used to determine if it is a Mifare Ultralight AES chip (if not, abort).

- Page 0x04 is read. If it is all zeroes, the chip is considered un-encoded (abort). If it contains a value that
  corresponds to the ``public_id`` of a known key set, this key set is used for all further operations. If it contains
  a different value, we consider this chip to belong to a different organizer or not to a pretix system at all (abort).

- An authentication with the chip using the UID key is performed.

- The UID of the chip will be read.

- The chip-specific key will be derived using the mechanism described above in the encoding step.

- An authentication with the chip using the chip-specific key is performed. If this is fully successful, this step
  proves that the chip knows the same chip-specific key as we do and is therefore an authentic chip encoded by us and
  we can trust its UID value.

- The UID is transmitted to the server to fetch the correct medium.

During these steps, the keys are never transmitted in plain text and can thus not be sniffed by a nearby attacker
with a strong antenna.

.. _Mifare Ultralight AES: https://www.nxp.com/products/rfid-nfc/mifare-hf/mifare-ultralight/mifare-ultralight-aes-enhanced-security-for-limited-use-contactless-applications:MF0AESx20
.. _data sheet: https://www.nxp.com/docs/en/data-sheet/MF0AES(H)20.pdf
.. _AN10922: https://www.nxp.com/docs/en/application-note/AN10922.pdf