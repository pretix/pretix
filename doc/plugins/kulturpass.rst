KulturPass
==========

.. note::

    Since the KulturPass is specific to event organizers within Germany, the following page is also  only provided in
    German. Should you require assistance with the KulturPass and do not speak this language, please feel free reach
    out to support@pretix.eu.


Einführung
----------
Der `KulturPass`_ ist ein Angebot der Bundesregierung für alle, die im laufenden Jahr ihren 18. Geburtstag feiern.
Sie erhalten ab ihrem 18. Geburtstag ein Budget von 200 Euro, das sie für Eintrittskarten, Bücher, CDs, Platten und
vieles andere einsetzen können. So wird Kultur vor Ort noch einfacher erlebbar. Gleichzeitig stärkt das die Nachfrage
bei den Anbietenden.

Da pretix ein Ticketing-System ist, stellen wir ausschließlich einen automatisierten Prozess für den Verkauf von
Eintrittskarten über den KulturPass-Marktplatz bereit.


Registrierung und Einrichtung
-----------------------------
Um als Unternehmen oder Kultureinrichtung Angebote auf dem KulturPass-Marktplatz anbieten zu können, ist zunächst eine
Registerung und die Einrichtung eines "Shops" sowie der dazugehörigen Angebote notwendig.

1. Registrierung
    Registrieren Sie sich zunächst unter https://www.kulturpass.de/anbietende/layer als Anbieter. Im Zuge der
    Registrierung beantworten Sie einige Fragen zu Ihrem Unternehmen/Ihrer Kultureinrichtung, hinterlegen Ihre
    E-Mail-Adresse und beantworten Fragen zu Ihren Angebotsformen sowie Finanzierung Ihrer Einrichtung.

2. Anlegen eines KulturPass Shops
    Nach Ihrer Registrierung müssen Sie der Weitergabe Ihrer Daten an die technische Platform hinter dem KulturPass,
    Mirakl, zustimmen. Hier benennen Sie auch Ihren Shop.

3. Identifizierung mit ELSTER-Zertifikat
    Als nächsten Schritt müssen Sie Ihr Unternehmen oder Ihre Einrichtung mit Hilfe eines sog. ELSTER-Zertifikates
    identifizieren. Dieses Zertifikat nutzen Sie auch bereits jetzt schon, wenn Sie auf elektronischem Wege mit der
    Finanzverwaltung kommunizieren.

4. Ersteinrichtung in pretix
    Hinterlegen Sie nun die ID-Nummer Ihres KulturPass Marktplatz-Shops sowie einen API-Key in den
    `Einstellungen Ihres Veranstalterkontos`_ (Veranstalter-Konto -> Einstellungen -> KulturPass). Diese Daten müssen
    Sie nur einmalig für alle Ihre Veranstaltungen angeben.

    Im `KulturPass-Backend`_ finden Sie die benötigten Informationen indem Sie auf das Benutzer-Symbol in der oberen,
    rechten Ecke klicken, "Profil" und dann "API Schlüssel" auswählen bzw. indem Sie auf "Einstellungen" in der
    Navigation links und dann "Shop" auswählen.

.. note::

    Zu jedem Zeitpunkt kann nur ein Hintergrundsystem mit dem KulturPass-System verbunden sein. Werden
    unterschiedliche Systeme oder gar mehrere pretix-Veranstalterkonten mit dem gleichen KulturPass-System verbunden,
    können keine Bestellungen mehr verarbeitet werden und Angebote nicht automatisiert an den KulturPass-Marktplatz
    übermittelt werden. Eingehende Bestellungen von Jugendlichen werden in diesem Fall automatisch abgelehnt, da diese
    nicht eindeutig zugeordnet werden können. Ebenso überschreibt die Bereitstellung der Angebote eines Systems die
    Angebote eines anderen Systems.

    Wenn Sie mehrere Systeme haben, die den KulturPass-Marktplatz bedienen sollen, wenden Sie sich bitte an den
    KulturPass-Support, um sich einen weiteren Shop einrichten zu lassen.

5. Aktivierung der KulturPass-Erweiterungen
    Alle Veranstaltungen, die Sie über den KulturPass anbieten möchten, benötigen die `KulturPass-Erweiterung`_.
    Aktivieren Sie diese bitte in jeder relevanten Veranstaltung über Einstellungen -> Erweiterungen -> Tab
    "Integrationen" -> KulturPass.

6. Konfiguration der Artikel
    Nachdem die KulturPass-Erweiterung aktiviert wurde, müssen Sie sich entscheiden, welche Produkte Sie über den
    KulturPass-Marktplatz anbieten möchten. In der Bearbeitungs-Ansicht des jeweiligen Produktes finden Sie hierzu im
    Tab "Zusätzliche Einstellungen" eine Checkbox "Das Produkt kann mit dem KulturPass erworben werden".

.. note::

    Die Eigenschaft, dass ein Produkt durch den KulturPass-Marktplatz erworben werden kann, kann für beliebig viele
    Produkte aktiviert werden. Auf Grund der Funktionsweise des KulturPasses sollten Sie jedoch gerade bei vielen
    Artikeln mit unterschiedlich hohen Preisen darauf achten, dass die Preisspanne nicht zu hoch ausfällt.

    Aktivieren Sie die Option für drei Produkte für 1, 10 und 100 Euro, so wird Ihr Angebot im KulturPass-Marktplatz
    für 100 Euro gelistet werden. Dies bedeutet im Umkehrschluss auch, dass das KulturPass-Guthaben eines Jugendlichen
    auch mindestens 100 Euro betragen muss, damit er Ihr Angebot in Anspruch nehmen kann - auch wenn die betroffene
    Person lediglich das 1 Euro-Angebot wahrnehmen möchte. Erst mit dem 100 Euro KulturPass-Einlösecode wählt die
    kaufende Person in Ihrem pretix-Shop aus, welches Produkt erworben werden soll. Ein Restguthaben wird nach dem Kauf
    automatisch zurückerstattet und dem KulturPass-Konto wieder gutgeschrieben.

7. Konfiguration des Marktplatz-Eintrages
    Je nach dem, ob es sich bei Ihrer Veranstaltung um eine Einzelveranstaltung oder eine Veranstaltungsreihe handelt,
    müssen Sie die folgende Einstellung einmalig oder pro Veranstaltungstermin vornehmen.

    Einzelveranstaltungen konfigurieren Sie über den Menüpunkt "KulturPass" in den Einstellungen Ihrer Veranstaltung;
    Veranstaltungsreihen beim Anlegen oder Editieren eines jeden einzelnen Termins am Ende der Seite.

    Um eine Veranstaltung oder einen Veranstaltungstermin im KulturPass-Marktplatz anzubieten, aktivieren Sie zunächst
    die Option "Diese Veranstaltung via KulturPass anbieten". Geben Sie im folgenden die benötigten Informationen an.

    Bitte beachten Sie, dass Sie bei den Angaben präzise Titel und Beschreibungen verwenden, da der KulturPass-
    Marktplatz ausschließlich die Informationen aus diesem Bereich verwendet. Etwaige andere Informationen die Sie
    bspw. in den "Text auf Startseite"-Felder eingeben haben, erreichen das KulturPass-System nicht.

.. note::

    Gerade bei Veranstaltungsreihen nutzen viele pretix-Veranstalter gerne verkürzte Termin-Namen. Ein Schwimmbad würde
    beispielsweise Ihre Veranstaltungsreihe "Freibad Musterstadt" und die einzelnen Termine nur "Schwimmen" nennen.

    Während dies im pretix-Shop in einem gemeinsamen Kontext wunderbar funktioniert, würde eine Veranstaltung mit dem
    Titel "Schwimmen" im KulturPass-Marktplatz Informationen vermissen lassen. Wählen Sie daher für das Eingabefeld
    "Veranstaltungstitel" in der KulturPass-Konfiguration einen sprechenden Wert.

8. Übermittlung der Angebote
    Sobald Sie Ihre ersten Veranstaltungen konfiguriert und live geschaltet haben, übermittelt pretix automatisch in
    regelmäßigen Abständen alle von Ihnen angebotenen Veranstaltungen an das KulturPass System (Mirakl). Bitte beachten
    Sie jedoch, dass der Import der Produkte und Angebote einige Zeit in Anspruch nehmen kann. Zum einen müssen
    Angebote initial händisch von den Betreibern der KulturPass-Platform freigegeben werden, zum anderen muss auch eine
    Synchronisation zwischen dem Hintergrundsystem und der KulturPass-App erfolgen. Auf die Dauer dieser Prozesse hat
    pretix keinen Einfluss.

9. Freischalten des Marktplatz-Shops
    Nachdem pretix erstmalig Angebote an das KulturPass-System übermittelt hat, müssen Sie Ihren Shop KulturPass-Shop
    einmalig freischalten. Loggen Sie sich hierzu in das `KulturPass-Backend`_ ein.


Verwalten von KulturPass-Bestellungen
-------------------------------------
Durch die Nutzung der pretix-Integration mit dem KulturPass-System müssen Sie sich - bis auf die Kennzeichnung von
Produkten, die per KulturPass erworben werden dürfen, sowie die Bereitstellung von Veranstaltungs-Informationen für den
KulturPass-Marktplatz - um nichts kümmern: pretix übermittelt automatisch Ihre Veranstaltungen, wickelt die Einlösung
der Tickets ab und führt die Abrechnung mit dem Hintergrund-System durch.

Für Ihre Kunden verhält sich der KulturPass wie eine Zahlungsmethode im Bestellprozess und wird dort neben Ihren
anderen Zahlungsmethoden mit angeboten.

Die Gelder für mit dem KulturPass bezahlte Tickets erhalten Sie in Form einer Sammel-Überweisung von der Stiftung
Digitale Chancen auf das von Ihnen beim KulturPass Onboarding angegeben Bankkonto.

In Ihrem `KulturPass-Backend`_ können Sie über den Menüpunkt "Buchhaltung" Ihre bereits erfolgten und kommenden
Auszahlungen betrachten.

.. note::

    Es ist von äußerster Wichtigkeit, dass Sie weder die eingehenden Bestellungen noch die Produkte und Angebote im
    KulturPass-Backend händisch bearbeiten - auch wenn dies möglich wäre.

    Bei händischen Änderungen riskieren Sie, dass die Datenbasis zwischen pretix und dem KulturPass-System divergiert
    und es zu fehlerhaften Buchungen kommt. Wann immer möglich, sollten Sie Korrekturbuchungen und Änderungen
    ausschließlich über pretix vornehmen.

    Sollte eine händische Änderung/Korrektur notwendig werden, wenden Sie sich bitte an den pretix-Support, damit wir
    die Auswirkungen evaluieren und vorab mit Ihnen besprechen können!

Erstattungen für Stornos und Absagen können Sie wie gehabt über das pretix-Backend vornehmen. Der jeweilige Betrag wird
dem KulturPass-Konto dann automatisch gutgeschrieben.

Da nach Ausgabe eines KulturPass Einlöse-Codes dieser vom Kunden jederzeit oder vom System bei
Nicht-(Komplett)Einlösung binnen 48 Stunden storniert werden kann, kann das im KulturPass-Backend angezeigte,
auszuzahlende Guthaben fluktuieren. Da in der Regel Auszahlungen frühestens 48 Stunden nach der Aufgabe einer
KulturPass-Bestellungen erfolgen, sollte Ihr Guthaben in der Regel nicht ins Negative gehen.

Ablauf für Kunden
-----------------
Ihre Kunden erhalten - nachdem sie sich ein eigenes Konto in der KulturPass-App angelegt und sich mit ihrem
elektronischen Personalausweis identifiziert haben - ein Guthaben von 200 Euro, welches für Leistungen aus dem
KulturPass-Marktplatz eingelöst werden kann.

Im Falle von Veranstaltungen, die per pretix verkauft werden, wählt der Kunde ein Angebot aus und erhält im folgenden
binnen kurzer Zeit (ca. 10-20 Minuten) einen Code und einen Link, um diesen einzulösen. Der Link bringt den Kunden direkt auf die Seite der
betreffenden pretix-Veranstaltung. Hier wird der Kunde darauf hingewiesen, für welche Produkte der Code genutzt werden
kann.

Im Bezahlschritt des Verkaufsprozesses wird dem Kunden vorgeschlagen, seinen KulturPass Einlösecode nun zu nutzen, um
die gewünschte Leistung zu erhalten.

Wurde ein Artikel gewählt, welcher günstiger als der Wert des Einlösecodes war, wird das Restguthaben automatisch auf
das KulturPass-Konto erstattet.

Wurden hingegen mehrere Artikel in den Warenkorb gelegt, so kann die Differenz mit einem anderen, regulären
Zahlungsmittel erfolgen.

Einlösecodes, die vom Kunden nicht binnen 48 Stunden eingelöst werden, werden automatisch storniert und dem
KulturPass-Konto wieder gutgeschrieben. Dieser Mechanismus greift auch, wenn eine Veranstaltung mittlerweile
ausverkauft ist und daher der Einlösecode nicht mehr Nutzbar ist.


Unterstützung
-------------
Weitergehende Informationen zum KulturPass finden Sie auch auf der `Webseite des KulturPasses`_, sowie im
`KulturPass Serviceportal`_.


.. _KulturPass: https://www.kulturpass.de/
.. _Einstellungen Ihres Veranstalterkontos: https://pretix.eu/control/organizer/-/settings/kulturpass
.. _KulturPass-Erweiterung: https://pretix.eu/control/event/-/-/settings/plugins#tab-0-2-open
.. _KulturPass-Backend: https://kulturpass-de.mirakl.net/
.. _Webseite des KulturPasses: https://www.kulturpass.de/
.. _KulturPass Serviceportal: https://service.kulturpass.de/help/