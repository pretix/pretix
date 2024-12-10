.. highlight:: ini
.. spelling:word-list::

   IdP
   skIDentity
   ePA
   NPA

Presale SAML Authentication
===========================

The Presale SAML Authentication plugin is an advanced plugin, which most event
organizers will not need to use. However, for the select few  who do require
strong customer authentication that cannot be covered by the built-in customer
account functionality, this plugin allows pretix to connect to a SAML IdP and
perform authentication and retrieval of user information.

Usage of the plugin is governed by two separate sets of settings: The plugin
installation, the Service Provider (SP) configuration and the event
configuration.

Plugin installation and initial configuration
---------------------------------------------

.. note:: If you are a customer of our hosted `pretix.eu`_ offering, you can
          skip this section.

The plugin is installed as any other plugin in the pretix ecosystem. As a
pretix system administrator, please follow the instructions in the the
:ref:`Administrator documentation <admindocs>`.

Once installed, you will need to assess, if you want (or need) your pretix
instance to be a single SP for all organizers and events or if every event
organizer has to provide their own SP.

Take the example of a university which runs pretix under an pretix Enterprise
agreement. Since they only provide ticketing services to themselves (every
organizer is still just a different department of the same university), a
single SP should be enough.

On the other hand, a reseller such as `pretix.eu`_ who services a multitude
of clients would not work that way. Here, every organizer is a separate
legal entity and as such will also need to provide their own SP configuration:
Company A will expect their SP to reflect their company - and not a generalized
"pretix SP".

Once you have decided on the mode of operation, the :ref:`Configuration file
<config>` needs to be extended to reflect your choice.

Example::

    [presale-saml]
    level=global

``level``
    ``global`` to use only a single, system-wide SP, ``organizer`` for multiple
    SPs, configured on the organizer-level. Defaults to ``organizer``.

Service Provider configuration
------------------------------

Global Level
^^^^^^^^^^^^

.. note:: If you are a customer of our hosted `pretix.eu`_ offering, you can
          skip this section and follow the instructions on the upcoming
          Organizer Level settings.

As a user with administrative privileges, please activate them by clicking the
`Admin Mode` button in the top right hand corner.

You should now see a new menu-item titled `SAML` appear.

Organizer Level
^^^^^^^^^^^^^^^

Navigate to the organizer settings in the pretix backend. In the navigation
bar, you will find a menu-item titled `SAML` if your user has the `Can
change organizer settings` permission.


.. note:: If you are a customer of our hosted `pretix.eu`_ offering, the menu
          will only appear once one of our friendly customer service agents
          has enabled the Presale SAML Authentication plugin for at least one
          of your events. Feel free to get in touch with us!

Setting up the SP
^^^^^^^^^^^^^^^^^

No matter where your SP configuration lives, you will be greeted by a very
long list of fields of which almost all of them will need to be filled. Please
don't be discouraged - most of the settings don't need to be decided by yourself
and/or are already preset with a sensible default setting.

If you are not sure what setting you should choose for any of the fields, you
should reach out to your IdP operator as they can tell you exactly what the IdP
expects and - more importantly - supports.

``IdP Metadata URL``
    Please provide the URL where your IdP outputs its metadata. For most IdPs,
    this URL is static and the same for all SPs. If you are a member of the
    DFN-AAI, you can find the meta-data for the `Test-, Basic- and
    Advanced-Federation`_ on their website. Please do talk with your local
    IdP operator though, as you might not even need to go through the DFN-AAI
    and might just use your institutions local IdP which will also host their
    metadata on a different URL.

    The URL needs to be publicly accessible, as saving the settings form will
    fail if the IdP metadata cannot be retrieved. pretix will also automatically
    refresh the IdP metadata on a regular basis.

``SP Entity Id``
    By default, we recommend that you use the system-proposed metadata-URL as
    the Entity Id of your SP. However, if so desired or required by your IdP,
    you can also set any other, arbitrary URL as the SP Entity Id.

``SP Name / SP Decription``
    Most IdP will display the name and description of your SP to the users
    during authentication. The description field can be used to explain to the
    users how their data is being used.

``SP X.509 Certificate / SP X.509 Private Key``
    Your SP needs a certificate and a private key for said certificate. Please
    coordinate with your IdP, if you are supposed to generate these yourself or
    if they are provided to you.

``SP X.509 New Certificate``
    As certificates have an expiry date, they need to be renewed on a regular
    basis. In order to facilitate the rollover from the expiring to the new
    certificate, you can provide the new certificate already before the expiration
    of the existing one. That way, the system will automatically use the correct
    one. Once the old certificate has expired and is not used anymore at all,
    you can move the new certificate into the slot of the normal certificate and
    keep the new slot empty for your next renewal process.

``Requested Attributes``
    An IdP can hold a variety of attributes of an authenticating user. While
    your IdP will dictate which of the available attributes your SP can consume
    in theory, you will still need to define exactly which attributes the SP
    should request.

    The notation is a JSON list of objects with 5 attributes each:

      * ``attributeValue``: Can be defaulted to ``[]``.
      * ``friendlyName``: String used in the upcoming event-level settings to
        retrieve the attributes data.
      * ``isRequired``: Boolean indicating whether the IdP must enforce the
        transmission of this attribute. In most cases, ``true`` is the best
        choice.
      * ``name``: String of the internal, technical name of the requested
        attribute. Often starting with ``urn:mace:dir:attribute-def:``,
        ``urn:oid:`` or ``http://``/``https://``.
      * ``nameFormat``: String describing the type of ``name`` that has been
        set in the previous section. Often starting with
        ``urn:mace:shibboleth:1.0:`` or ``urn:oasis:names:tc:SAML:2.0:``.

    Your IdP can provide you with a list of available attributes. See below
    for a sample configuration in an academic context.

    Note, that you can have multiple attributes with the same ``friendlyName``
    but different ``name`` value. This is often used in systems, where the same
    information (for example a persons name) is saved in different fields -
    for example because one institution is returning SAML 1.0 and other
    institutions are returning SAML 2.0 style attributes. Typically, this only
    occurs in mix environments like the DFN-AAI with a large number of
    participants. If you are only using your own institutions IdP and not
    authenticating anyone outside of your realm, this should not be a common
    sight.

``Encrypt/Sign/Require ...``
    Does what is says on the box - please inquire with your IdP for the
    necessary settings. Most settings can be turned on as they increase security,
    however some IdPs might stumble over some of them.

``Signature / Digest Algorithm``
    Please chose appropriate algorithms, that both pretix/your SP and the IdP
    can communicate with. A common source of issues when connecting to a
    Shibboleth-based IdP is the Digest Algorithm: pretix does not support
    ``http://www.w3.org/2009/xmlenc11#rsa-oaep`` and authentication will fail
    if the IdP enforces this.

``Technical/Support Contacts``
    Those contacts are encoded into the SPs public meta data and might be
    displayed to users having trouble authenticating. It is recommended to
    provide a dedicated point of contact for technical issues, as those will
    be the ones to change the configuration for the SP.

Event / Authentication configuration
------------------------------------

Basic settings
^^^^^^^^^^^^^^

Once the plugin has been enabled for a pretix event using the Plugins-menu from
the event's settings, a new *SAML* menu item will show up.

On this page, the actual authentication can be configured.

``Checkout Explanation``
    Since most users probably won't be familiar with why they have to authenticate
    to buy a ticket, you can provide them a small blurb here. Markdown is supported.

``Attribute RegEx``
    By default, any successful authentication with the IdP will allow the user to
    proceed with their purchase. Should the allowed audience needed to be restricted
    further, a set of regular Expressions can be used to do this.

    An Attribute RegEx of ``{}`` will allow any authenticated user to pass.

    A RegEx of ``{ "affiliation": "^(employee@pretix.eu|staff@pretix.eu)$" }`` will
    only allow user to pass which have the ``affiliation`` attribute and whose
    attribute either matches ``employee@pretix.eu`` or ``staff@pretix.eu``.

    Please make sure that the attribute you are querying is also requested from the
    IdP in the first place - for a quick check you can have a look at the top of
    the page where all currently configured attributes are listed.

``RegEx Fail Explanation``
    Only used in conjunction with the above Attribute RegEx. Should the user not
    pass the restrictions imposed by the regular expression, the user is shown
    this error-message.

    If you are - for example in an university context - restricting access to
    students only, you might want to explain here that Employees are not allowed
    to book tickets.

``Ticket Secret SAML Attribute``
    In very specific instances, it might be desirable that the ticket-secret is
    not the randomly one generated by pretix but rather based on one of the
    users attributes - for example their unique ID or access card number.

    To achieve this, the name of a SAML-attribute can be specified here.

    It is however necessary to note, that even with this setting in use,
    ticket-secrets need to be unique. This is why when this setting is enabled,
    the default, pretix-generated ticket-secret is prefixed with the attributes
    value.

    Example: A users ``cardid`` attribute has the value of ``01189998819991197253``.
    The default random ticket secret would have been
    ``yczygpw9877akz2xwdhtdyvdqwkv7npj``. The resulting new secret will now be
    ``01189998819991197253_yczygpw9877akz2xwdhtdyvdqwkv7npj``.

    That way, the ticket secret is still unique, but when checking into an event,
    the user can easily be searched and found using their identifier.

IdP-provided E-Mail addresses, names
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default, pretix will only authenticate the user and not process the received
data any further.

However, there are a few exceptions to this rule.

There are a few `magic` attributes that pretix will use to automatically populate
the corresponding fields within the checkout process **and lock them out from
user editing**.

  * ``givenName`` and ``sn``: If both of those attributes are present and pretix
    is configured to collect the users name, these attributes' values are used
    for the given and family name respectively.
  * ``email``: If this attribute is present, the E-Mail-address of the users will
    be set to the one transmitted through the attributes.

The latter might pose a problem, if the IdP is transmitting an ``email`` attribute
which does contain a system-level mail address which is only used as an internal
identifier but not as a real mailbox. In this case, please consider setting the
``friendlyName`` of the attribute to a different value than ``email`` or removing
this field from the list of requested attributes altogether.

Saving attributes to questions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By setting the ``internal identifier`` of a user-defined question to the same name
as a SAML attribute, pretix will save the value of said attribute into the question.

All the same as in the above section on E-Mail addresses, those fields become
non-editable by the user.

Please be aware that some specialty question types might not be compatible with
the SAML attributes due to specific format requirements. If in doubt (or if the
checkout fails/the information is not properly saved), try setting the question
type to a simple type like "Text (one line)".

Notes and configuration examples
--------------------------------

Requesting SAML 1.0 and 2.0 attributes from an academic IdP
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This requests the ``eduPersonPrincipalName`` (also sometimes called EPPN),
``email``, ``givenName`` and ``sn`` both in SAML 1.0 and SAML 2.0 attributes.

.. sourcecode:: json

    [
        {
            "attributeValue": [],
            "friendlyName": "eduPersonPrincipalName",
            "isRequired": true,
            "name": "urn:mace:dir:attribute-def:eduPersonPrincipalName",
            "nameFormat": "urn:mace:shibboleth:1.0:attributeNamespace:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "eduPersonPrincipalName",
            "isRequired": true,
            "name": "urn:oid:1.3.6.1.4.1.5923.1.1.1.6",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "email",
            "isRequired": true,
            "name": "urn:mace:dir:attribute-def:mail",
            "nameFormat": "urn:mace:shibboleth:1.0:attributeNamespace:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "email",
            "isRequired": true,
            "name": "urn:oid:0.9.2342.19200300.100.1.3",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "givenName",
            "isRequired": true,
            "name": "urn:mace:dir:attribute-def:givenName",
            "nameFormat": "urn:mace:shibboleth:1.0:attributeNamespace:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "givenName",
            "isRequired": true,
            "name": "urn:oid:2.5.4.42",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "sn",
            "isRequired": true,
            "name": "urn:mace:dir:attribute-def:sn",
            "nameFormat": "urn:mace:shibboleth:1.0:attributeNamespace:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "sn",
            "isRequired": true,
            "name": "urn:oid:2.5.4.4",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        }
    ]

skIDentity IdP Metadata URL
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Since the IdP Metadata URL for `skIDentity`_ is not readily documented/visible
in their backend, we document it here:
``https://service.skidentity.de/fs/saml/metadata``

Requesting skIDentity attributes for electronic identity cards
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This requests the basic ``eIdentifier``, ``IDType``, ``IDIssuer``, and
``NameID`` from the `skIDentity`_ SAML service, which are available for
electronic ID cards such as the German ePA/NPA. (Other attributes such as
the name and address are available at additional cost from the IdP).

.. sourcecode:: json

    [
        {
            "attributeValue": [],
            "friendlyName": "eIdentifier",
            "isRequired": true,
            "name": "http://www.skidentity.de/att/eIdentifier",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "IDType",
            "isRequired": true,
            "name": "http://www.skidentity.de/att/IDType",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "IDIssuer",
            "isRequired": true,
            "name": "http://www.skidentity.de/att/IDIssuer",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        },
        {
            "attributeValue": [],
            "friendlyName": "NameID",
            "isRequired": true,
            "name": "http://www.skidentity.de/att/NameID",
            "nameFormat": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
        }
    ]

.. _pretix.eu: https://pretix.eu
.. _Test-, Basic- and Advanced-Federation: https://doku.tid.dfn.de/en:metadata
.. _skIDentity: https://www.skidentity.de/