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
       tour, a theatre group playing the same play multiple times, etc.
   * - | |:gb:| **Date**
       | |:de:| Termin
       | |:wrench:| Subevent
     - A date represents a single real-world event inside an event series. Dates can differ from each other in name,
       date, time, location, pricing, capacity, and seating plans, but otherwise share the same configuration.
   * - | |:gb:| **Organizer**
       | |:de:| Veranstalter
     - An organizer represents the entity using pretix, usually the company or insitution running one or multiple events.
       In terms of navigation in the system, organizers are the "middle layer" between the system itself and the specific
       events.
       Multiple organizers on the same pretix system are fully separated from each other with very few exceptions.
   * - | |:gb:| **Product**
       | |:de:| Produkt
       | |:wrench:| Item
     - A product is anything that can be sold, such as a specific type of ticket or merchandise.
   * - | |:gb:| **Variation**
       | |:de:| Variante
       | |:wrench:| Item variation
     - Some products come in multiple variations that can differ in description, price and capacity. Examples would
       include "Adult" and "Child" in case of a concert ticket, or "S", "M", "L", … in case of a t-shirt product.
   * - | |:gb:| **Category**
       | |:de:| Kategorie
     - Products can be grouped together in categories. This is mostly to organize them cleanly in the frontend if you
       have lots of them.
   * - | |:gb:| **Add-on product**
       | |:de:| Zusatzprodukt
     - An add-on product 
   * - | |:gb:| **Bundled product**
       | |:de:| Enthaltenes Produkt
     - Products can be grouped together in categories. This has
   * - | |:gb:| **Quota**
       | |:de:| Kontingent
     - Foo
   * - | |:gb:| **Question**
       | |:de:| Frage
     - Foo
   * - | |:gb:| **Voucher**
       | |:de:| Gutschein
     - Foo
   * - | |:gb:| **Gift card**
       | |:de:| Geschenkgutschein
     - Foo
   * - | |:gb:| **Order**
       | |:de:| Bestellung
     - Foo
   * - | |:gb:| **Order position**
       | |:de:| Bestellposition
     - Foo
   * - | |:gb:| **Attendees**
       | |:de:| Teilnehmende
     - Foo
   * - | |:gb:| **Invoice**
       | |:de:| Rechnung
     - Foo
   * - | |:gb:| **Check-in**
       | |:de:| Check-in
     - Foo
   * - | |:gb:| **Check-in list**
       | |:de:| Check-in-Liste
     - Foo
   * - | |:gb:| **Tax rule**
       | |:de:| Steuer-Regel
     - Foo
   * - | |:gb:| **Ticket**
       | |:de:| Ticket
     - Foo
   * - | |:gb:| **Badge**
       | |:de:| Badge
     - Foo
   * - | |:gb:| **Team**
       | |:de:| Team
     - Foo
   * - | |:gb:| **User**
       | |:de:| Benutzer
     - Foo
   * - | |:gb:| **Device**
       | |:de:| Gerät
     - Foo
   * - | |:gb:| **Gate**
       | |:de:| Position
     - Foo
   * - | |:gb:| **Widget**
       | |:de:| Widget
     - Foo
   * - | |:gb:| **Box office**
       | |:de:| Abendkasse
     - Foo
   * - | |:gb:| **Exhibitor**
       | |:de:| Aussteller
     - Foo
   * - | |:gb:| **Reseller**
       | |:de:| Vorverkaufsstelle
     - Foo
