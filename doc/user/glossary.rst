Glossary
========

This page gives definitions of domain-specific terms that we use a lot inside pretix and that might be used slightly
differently elsewhere, as well as their official translations to other languages. In some cases, things have a different
name internally, which is noted with a |:wrench:| symbol. If you only use pretix, you'll never see these, but if you're
going to develop around pretix, for example connect to pretix through our API, you need to know these as well.



.. rst-class:: rest-resource-table

.. list-table:: Glossary
   :widths: 15 30
   :header-rows: 1

   * - Term
     - Definition
   * - | |:gb:| **Organizer**
       | |:de:| Veranstalter
     - An organizer represents the entity using pretix, usually the company or institution running one or multiple events.
       In terms of navigation in the system, organizers are the "middle layer" between the system itself and the specific
       events.
       Multiple organizers on the same pretix system are fully separated from each other with very few exceptions.
   * - | |:gb:| **Event**
       | |:de:| Veranstaltung
     - An event is the central entity in pretix that you and your customers interact with all the time. An event
       represents one **shop** in which things like tickets can be bought. Since the introduction of event series (see
       below), this might include multiple events in the real world.

       Every purchase needs to be connected to an event, and most things are completely separate between different
       events, i.e. most actions and configurations in pretix are done per-event.
   * - | |:gb:| **Event series**
       | |:de:| Veranstaltungsreihe
     - An event series is one of two types of events. Unlike a non-series event, an event series groups together
       multiple real-world events into one pretix shop. Examples are time-slot-based booking for a museum, a band on
       tour, a theater group playing the same play multiple times, etc.
   * - | |:gb:| **Date**
       | |:de:| Termin
       | |:wrench:| Subevent
     - A date represents a single real-world event inside an event series. Dates can differ from each other in name,
       date, time, location, pricing, capacity, and seating plans, but otherwise share the same configuration.
   * - | |:gb:| **Product**
       | |:de:| Produkt
       | |:wrench:| Item
     - A product is anything that can be sold, such as a specific type of ticket or merchandise.
   * - | |:gb:| **Admission product**
       | |:de:| Zutrittsprodukt
     - A product is considered an **admission product** if its purchase represents a person being granted access to your
       event. This applies to most ticketing products, but not e.g. to merchandise.
   * - | |:gb:| **Variation**
       | |:de:| Variante
       | |:wrench:| Item variation
     - Some products come in multiple variations that can differ in description, price and capacity. Examples would
       include "Adult" and "Child" in case of a concert ticket, or "S", "M", "L", … in case of a t-shirt product.
   * - | |:gb:| **Category**
       | |:de:| Kategorie
     - Products can be grouped together in categories. This is mostly to organize them cleanly in the frontend if you
       have lots of them.
   * - | |:gb:| **Quota**
       | |:de:| Kontingent
     - A quota is a capacity pool that defines how many times a product can be sold. A quota can be connected to multiple
       products, in which case all of them are counted together. This is useful e.g. if you have full-price and reduced
       tickets and only want to sell a certain number of tickets in total. The same way, multiple quotas can be connected
       to the same product, in which case the ticket will be available as long as all of them have capacity left.
   * - | |:gb:| **Add-on product**
       | |:de:| Zusatzprodukt
     - An add-on product is a product that is purchased as an upgrade or optional addition to a different product.
       Examples would be include a conference ticket that optionally allows to buy a public transport ticket for the
       same day, or a family ticket for 4 persons that allows you to add additional persons at a small cost, or a
       "two workshops" package that allows you to select two of a larger number of workshops at a discounted price.
       In all cases, there is a "main product" (the conference ticket, the family ticket) and a number of "add-on products"
       that can be chosen from.
   * - | |:gb:| **Bundled product**
       | |:de:| Enthaltenes Produkt
     - A bundled product is a product that is automatically put into the cart when another product is purchased. It's
       similar to an add-on product, except that the customer has no choice between whether it is added or which of a
       set of product is added.
   * - | |:gb:| **Question**
       | |:de:| Frage
     - A question is a custom field that customers need to fill in when purchasing a specific product.
   * - | |:gb:| **Voucher**
       | |:de:| Gutschein
     - A voucher is a code that can be used for multiple purposes: To grant a discount to specific customers, to only
       show certain products to certain customers, or to keep a seat open for someone specific even though you are
       sold out. If a voucher is used to apply a discount, the price of the purchased product is reduced by the
       discounted amount. Vouchers are connected to a specific event.
   * - | |:gb:| **Gift card**
       | |:de:| Geschenkgutschein
     - A :ref:`gift card <giftcards>` is a coupon representing an exact amount of money that can be used for purchases
       of any kind. Gift cards can be sold, created manually, or used as a method to refund your customer without paying
       them back directly.
       Unlike a voucher, it does not reduce the price of the purchased products when redeemed, but instead works as a
       payment method to lower the amount that needs to be paid through other methods. Gift cards are specific to an
       organizer by default but can even by shared between organizers.
   * - | |:gb:| **Cart**
       | |:de:| Warenkorb
     - A cart is a collection of products that are reserved by a customer who is currently completing the checkout
       process, but has not yet finished it.
   * - | |:gb:| **Order**
       | |:de:| Bestellung
     - An order is a purchase by a client, containing multiple different products. An order goes through various
       states and can change during its lifetime.
   * - | |:gb:| **Order code**
       | |:de:| Bestellnummer
     - An order code is the unique identifier of an order, usually consisting of 5 numbers and letters.
   * - | |:gb:| **Order position**
       | |:de:| Bestellposition
     - An order position is a single line inside an order, representing the purchase of one specific product. If the
       product is an admission product, this represents an attendee.
   * - | |:gb:| **Attendees**
       | |:de:| Teilnehmende
     - An attendee is the person designated to use a specific order position to access the event.
   * - | |:gb:| **Fee**
       | |:de:| Gebühr
     - A fee is an additional type of line inside an order that represents a cost that needs to be paid by the customer,
       but is not related to a specific product. A typical example is a shipping fee.
   * - | |:gb:| **Invoice** and **Cancellation**
       | |:de:| Rechnung und Rechnungskorrektur
     - An invoice refers to a legal document created to document a purchase for tax purposes. Invoices have individual
       numbers and no longer change after they have been issued. Every invoice is connected to an order, but an order
       can have multiple invoices: If an order changes, a cancellation document is created for the old invoice and a
       new invoice is created.
   * - | |:gb:| **Check-in**
       | |:de:| Check-in
     - A check-in is the event of someone being successfully scanned at an entry or exit of the event.
   * - | |:gb:| **Check-in list**
       | |:de:| Check-in-Liste
     - A check-in list is used to configure who can be scanned at a specific entry or exit of the event. Check-in lists
       are isolated from each other, so by default each ticket is valid once on every check-in list individually. They
       are therefore often used to represent *parts* of an event, either time-wise (e.g. conference days) or space-wise
       (e.g. rooms).
   * - | |:gb:| **Plugin**
       | |:de:| Erweiterung
     - A plugin is an optional software module that contains additional functionality and can be turned on and off per
       event. If you host pretix on your own server, most plugins need to be installed separately.
   * - | |:gb:| **Tax rule**
       | |:de:| Steuer-Regel
     - A tax rule defines how sales taxes are calculated for a product, possibly depending on type and country of the
       customer.
   * - | |:gb:| **Ticket**
       | |:de:| Ticket
     - A ticket usually refers to the actual file presented to the customer to be used at check-in, i.e. the PDF or
       Passbook file carrying the QR code. In some cases, "ticket" may also be used to refer to an order position,
       especially in case of admission products.
   * - | |:gb:| **Ticket secret**
       | |:de:| Ticket-Code
     - The ticket secret (sometimes "ticket code") is what's contained in the QR code on the ticket.
   * - | |:gb:| **Badge**
       | |:de:| Badge
     - A badge refers to the file used as a name tag for an attendee of your event.
   * - | |:gb:| **User**
       | |:de:| Benutzer
     - A user is anyone who can sign into the backend interface of pretix.
   * - | |:gb:| **Team**
       | |:de:| Team
     - A :ref:`team <user-teams>` is a collection of users who are granted some level of access to a set of events.
   * - | |:gb:| **Device**
       | |:de:| Gerät
     - A device is something that talks to pretix but does not run on a server. Usually a device refers to an
       installation of pretixSCAN, pretixPOS or some compatible third-party app on one of your computing devices.
   * - | |:gb:| **Gate**
       | |:de:| Station
     - A gate is a location at your event where people are being scanned, e.g. an entry or exit door. You can configure
       gates in pretix to group multiple devices together that are used in the same location, mostly for statistical
       purposes.
   * - | |:gb:| **Widget**
       | |:de:| Widget
     - The :ref:`widget` is a JavaScript component that can be used to embed the shop of an event or a list of events
       into a third-party web page.
   * - | |:gb:| **Sales channel**
       | |:de:| Verkaufskanal
     - A sales channel refers to the type in which a purchase arrived in the system, e.g. through pretix' web shop itself,
       or through other channels like box office or reseller sales.
   * - | |:gb:| **Box office**
       | |:de:| Abendkasse
     - Box office purchases refer to all purchases made in-person from the organizer directly, through a point of sale
       system like pretixPOS.
   * - | |:gb:| **Reseller**
       | |:de:| Vorverkaufsstelle
     - Resellers are third-party entities offering in-person sales of events to customers.
