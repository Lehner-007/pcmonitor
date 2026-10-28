# pcmonitor 0.6.0

## Entwicklungsstand 0.6.0

Die Netzwerkübersicht zeigt zusätzlich die vom Kernel gemeldeten Betriebs- und Linkzustände sowie verfügbare Linkwechselzähler. Einordnungstexte beschreiben nur die gelesenen Werte; sie behaupten weder eine Ursache noch die Erreichbarkeit eines Gegenübers.

Lesende Hardware-Bestandsaufnahme für Linux Mint / Cinnamon mit GTK 4.

## Start

Normal: `./.start.sh`

Erweiterte RAM-/Firmwareabfrage: `./start-admin.sh`

Der ausdrücklich gewählte Admin-Starter belässt die GUI beim normalen Benutzer. Pro erweiterter Erfassung startet höchstens ein `pkexec` einen festen Helfer, der `lshw -json` und `dmidecode --type 17` direkt ausführt. Jede Quelle hat eigenen Status, Rückgabecode und Erfassungszeitpunkt. Ablehnung erzeugt keine zweite Anfrage; normale Erfassung bleibt verfügbar. F5 fordert in diesem Modus eine neue Erfassung an; parallele Erfassungen sind gesperrt. Detailklick, Export und Geräteüberwachung erhöhen keine Rechte. .start.sh erhöht nichts. Nicht das ganze Programm mit sudo starten.

Der Helfer nutzt ausschließlich feste Systemwerkzeuge und System-Python mit `-I -S`, ohne Projekt-, Benutzer- oder sitecustomize-Imports. Werkzeuglaufzeit jeweils höchstens 20 Sekunden; gesamte Rechteanforderung einschließlich Dialog höchstens 120 Sekunden. Abbrechen oder Schließen beendet über den Steuerkanal die Werkzeug-Prozessgruppen. Bei Installation müssen Helfer, Interpreter, Standardbibliothek und Werkzeuge samt Pfaden root gehören und gegen Benutzeränderung geschützt sein; für installierte Helfer unter /usr oder /opt wird dies geprüft. Der Entwicklungsstand installiert keinen dauerhaften privilegierten Dienst. Die Zahl sichtbarer Passwortdialoge bestimmt PolicyKit; das Programm startet höchstens eine Rechteanforderung pro Erfassung.

CLI: `./.start.sh --help`, `--version`, `--author`. Autor ist nicht hinterlegt, wird nicht erfunden.

## Bedienung

Links 16 Bereiche mit vorhandenen 3D-Bildern aus `/home/josef/Bilder`. Bilder sind im Projekt mitgeliefert; keine Laufzeitabhängigkeit von diesem Ordner. Für Kartenleser steht ersatzweise das Speicherbild; ein eigenes Kartenleserbild war nicht vorhanden.

Rechts Daten, Suche und Filter Alle / Belegt / Leer / Nicht ermittelbar. CPU, Mainboard, Sensoren, System und Ereignisse haben keinen Belegungsfilter. Mainboard ist beim Start ausgewählt.

Ansicht → Bestandsaufnahme aktualisieren (F5). Datei → Ergebnisse exportieren schreibt einen UTF-8-TXT-Bericht über **alle** Bereiche, unabhängig von der aktuellen Anzeige. Persönliche Angaben (MAC/IP/SSID, Bluetooth-Aliasse, benutzerdefinierte Audio-Beschreibungen) und Ereignisse jeweils ausdrücklich auswählen; standardmäßig aus. Verfügbare Seriennummern stehen in Gerätedetails und werden nur mit persönlichen Angaben exportiert. Zusätzlich werden MAC-/IP-Muster in Gerätenamen und Ereignistexten ohne Opt-in entfernt. Hilfe → Hilfe (F1), Einstellungen und Protokoll nutzen die gemeinsame Projektvorlage.

Geräteänderungen starten je Datenquelle mit einer Baseline ab der ersten erfolgreichen Abfrage, werden im Arbeitsspeicher gesammelt und alle drei Sekunden geprüft. USB, Blockgeräte, Netzwerkstatus, DRM-Anschlüsse und Bluetooth-Adapter sowie BlueZ-Endgeräte werden unterstützt. Kein rückwirkender Verlauf; kurzzeitige Wechsel zwischen Abfragen können fehlen. Bluetooth-Endgeräteverbindungen werden über die lesende BlueZ-D-Bus-Schnittstelle erfasst. Bei vorübergehender Nichtverfügbarkeit bleibt der letzte Stand erhalten; es werden keine vermeintlichen Entfernungen erzeugt.

## Abhängigkeiten

Pflicht: Python 3.10+, python3-gi, gir1.2-gtk-4.0. Die übernommenen gemeinsamen Sprach-/Updatebausteine benötigen außerdem python3-requests und python3-bs4. Nichts wird automatisch installiert.

Optional: lshw (RAM-Module), pciutils/lspci (PCI-Namen), util-linux/lsblk (Laufwerke), iproute2/ip (IP-Adressen), x11-xserver-utils/xrandr (aktueller Monitor-Modus), iw (SSID/Signal/Bitraten), dmidecode (explizit mit Einheit gemeldete RAM-Geschwindigkeit, nur soweit lesbar), nvidia-smi (NVIDIA-VRAM über PCI-Adresse), pactl (Audio-Ein-/Ausgänge und Standardgerät), BlueZ-D-Bus-Dienst (Bluetooth-Endgeräte), dpkg-query (lshw-Paketversion), systemd-detect-virt (Virtualisierung), pkexec/PolicyKit (gesonderter Admin-Start). Fehlende Kernwerkzeuge und Abfragefehler stehen in Systeminformationen. Ohne iw bleiben SSID/Signal/Bitraten unbekannt; die fehlende Quelle wird diagnostiziert. GitHub-Quelle: https://github.com/Lehner-007/pcmonitor. Automatische Versionsprüfungen laufen nur, wenn sie aktiviert und laut Intervall fällig sind; die manuelle Prüfung bleibt verfügbar. Zusätzliche Sprachpakete werden nur auf Benutzeraktion geladen.

## Daten und Grenzen

/sys und /proc sind die primären Quellen. Prozesse starten ohne Shell mit festem Argumentvektor und begrenzter Laufzeit. Ausgaben werden nichtblockierend gelesen; die Prozessgruppenbereinigung umfasst Nachkommen und ist zeitlich begrenzt. Hardware-/Systemeinstellungen werden nicht verändert. Nur eigene Konfiguration, Protokolle und angeforderte Exporte werden geschrieben. Entwicklungsstart: `.config` im Projekt; direkter installierter Python-Start: XDG-Konfiguration des Benutzers.

Ein Linux-Gerätepfad ist keine nachgewiesene Gehäusebuchse. USB-Hubs, logische Netzwerkschnittstellen, DRM-Konnektoren und MMC-Hosts werden entsprechend gekennzeichnet. Nicht erkannte Geräte bedeuten **nicht Leer**. Nur explizit von lshw als leer gemeldete RAM-Bänke erhalten Leer. PCI-Steckplätze ohne zugeordnetes Endgerät bleiben unbekannt. Eine fest verbaute PCI-Bridge/Root-Port allein gilt nicht als belegte Karte. Die Art-Spalte unterscheidet Komponenten, Hubs, Hardwareadapter, virtuelle Schnittstellen, Laufwerke, Partitionen und echte Steckplatzdatensätze. Physische SATA-/M.2-/USB-Buchsen und Gehäusepositionen sind im Allgemeinen nicht zuverlässig lesbar.

RAM-Module hängen von Firmware und Leserechten ab. RAM-Quellwerte werden nicht durch Addition von 2^32 rekonstruiert. Unplausible lshw-Werte werden als unbekannte Geschwindigkeit mit Rohwert gekennzeichnet, plausible Taktwerte ausdrücklich unbestätigt; MHz und MT/s werden nicht gleichgesetzt. Explizit mit Einheit gemeldete dmidecode-Werte werden nur über einen eindeutigen Steckplatznamen zugeordnet. Firmwareangaben sind keine laufende physische Taktmessung. Vorhandene und Online-CPUs werden getrennt angegeben; Kernzahl stammt aus der Online-Topologie. CPU-Takt ist eine Momentaufnahme. BIOS-Modus ohne erkennbares EFI-Verzeichnis bleibt unbekannt. VRAM wird aus unterstützten sysfs-Attributen gelesen; ergänzend über nvidia-smi gelesen; GPUs werden über normalisierte PCI-Adressen zugeordnet. Ohne passende Quelle bleibt der Wert unbekannt. EDID liefert gegebenenfalls den Monitornamen; aktueller Modus/Hz aus XRandR nur bei gültiger, beidseitig eindeutiger EDID-Zuordnung. GPU-Adresse und DRM-Name bleiben sichtbar. Doppelte EDIDs, fehlende Daten oder getrennte Anschlüsse liefern keinen aktiven Modus. DRM-disconnected beweist keinen leeren Stecker (z. B. ausgeschalteter Monitor); daher weiter unbekannt. Unter Wayland eingeschränkt. Nicht rotierende Laufwerke werden als SSD/Flash oder virtuell bezeichnet, nicht als bewiesene physische SSD. Sensoren nur bei zugänglichen hwmon-Werten; der aufgelöste Gerätepfad unterscheidet gleichnamige NVMe-Sensoren. Kartenleser nur aus eindeutig benannten USB-Geräten oder MMC-Hosts; keine vollständige Modellliste. Fehlende Unterstützung wird sichtbar ausgewiesen.

## Prüfung

`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -v`

GUI-Prüfung in laufender Sitzung: `PYTHONPATH=. PYTHON_TEMPLATE_DEV=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/smoke_gui.py`

Der veröffentlichte Stand 0.5.4 enthält ein geprüftes DEB mit SHA-256-Prüfsumme. Die Testsuite und die manuellen Prüfungen auf dem Ziel-PC sind getrennt dokumentiert.

LAN: operstate, carrier und Linkgeschwindigkeit werden getrennt ausgelesen; der Adapterstatus behauptet keine Buchsenbelegung. WLAN: SSID nur mit Export-Opt-in, Signal sowie RX-/TX-Rate separat. Audio: ALSA-Hardwarebeschreibung plus verfügbare PulseAudio-/PipeWire-Ein-/Ausgänge, aktive Ports und Standardgerät; benutzerdefinierte Beschreibungen separat mit Opt-in. Keine Verbindung, Auswahl, Lautstärke oder Systemkonfiguration wird verändert.

## Nachprüfung 0.2.1

LAN-Ereignisse unterscheiden Betriebszustandsänderungen von carrier-Änderungen physischer Adapter. Virtuelle Adapter liefern keinen Kabelstatus. Ein unbekannter carrier bleibt unbekannt. Sensoren ergänzen verfügbare Modell- und Gerätebezeichnungen zum eindeutigen Gerätepfad; fehlende Modellangaben werden nicht geraten. Belegungsfilter erhalten Zeilen, für die keine Belegung anwendbar ist.

Die Exportmaskierung erkennt bekannte Adressmuster. Beliebige private Freitexte oder Seriennummern innerhalb fremder Gerätebezeichnungen können nicht zuverlässig erkannt werden. Export vor Weitergabe kontrollieren. Echte RAM-Geschwindigkeit, identische Monitor-EDIDs und die vollständige physische Buchsenbelegung bleiben hardwareabhängige Grenzen.

## Gerätedetails (0.3.0)

Ein Klick auf die Schaltfläche „Belegt“ öffnet Details für das zugeordnete Gerät. Mit Tab fokussieren und mit Eingabetaste oder Leertaste aktivieren. Leer, Nicht ermittelbar und Zeilen ohne Belegungszustand besitzen keine Detailaktion. Sortieren und Filtern verändern die Gerätezuordnung nicht.

Unterstützt werden belegte physische Monitoranschlüsse, erkannte belegte RAM-Bänke und zugeordnete PCIe-Steckplätze. USB-Komponenten, Laufwerke und virtuelle Schnittstellen werden dafür nicht künstlich als belegte Buchsen eingestuft. Details besitzen eine eigene Geräteüberschrift und Schließen-Schaltfläche.

Monitore: EDID-Herstellerkennung, Modell, DRM-Anschluss/Grafikkarte, eindeutige XRandR-Zuordnung, aktive und unterstützte Modi getrennt, ungefähre Abmessungen/Diagonale aus EDID und verfügbare Seriennummer. Ohne verifizierte XRandR-Zuordnung bleibt der aktive Modus unbekannt; verfügbare EDID-Basistimings werden ausdrücklich als unvollständige Modusliste gekennzeichnet. Gleichnamige Geräte werden über Anschluss und Geräteidentität unterschieden; identische EDIDs erlauben weiterhin keine XRandR-Zuordnung. Fehlende EDID verhindert das Öffnen eines nachweislich verbundenen Anschlusses nicht, schränkt aber die Erkennung eines Gerätetauschs am selben Anschluss ein.

Bei Monitoren und PCIe-Geräten wird vor dem Öffnen der aktuelle Zustand im Hintergrund geprüft. Solange deren Fenster offen ist, erfolgt dieselbe Prüfung im vorhandenen Abfrageintervall. RAM verwendet die unten beschriebene letzte bestätigte Erfassung. Bei Trennung, Austausch oder nicht mehr prüfbarem Zustand wird es ausdrücklich als veraltet gekennzeichnet; weitere Detailabfragen stoppen. Die zuletzt erfassten Werte bleiben als historische Bestandsaufnahme mit Zeitangabe lesbar. Die alte Detailaktion und der alte Detaildatensatz im Export entfallen. F5 erfasst den aktuellen Bestand erneut. Sehr kurze Steckwechsel zwischen zwei Abfragen können unerkannt bleiben.

RAM-Details verwenden ausschließlich die letzte bestätigte Erfassung im Arbeitsspeicher, auch wenn sie beim optionalen Admin-Start ermittelt wurde. Detailklick und offene RAM-Fenster starten keine neue Abfrage und keine Rechteerhöhung. PCIe-Nachprüfung verwendet vorhandene sysfs-Gerätekennungen; ein Austausch gegen ein identisches Gerät zwischen Abfragen ist damit nicht sicher erkennbar.

TXT-Exporte enthalten vorhandene Detailfelder unabhängig vom Ansichtsfilter. Detail-Seriennummern werden nur mit ausdrücklich gewähltem Export persönlicher Angaben aufgenommen. Allgemeine Freitext-Maskierungsgrenzen gelten weiterhin.

## RAM-Zwischenspeicher (0.3.1)

Modul-/Steckplatzkennung, belegter Zustand, Details, Erfassungszeitpunkt und tatsächlicher Abfragemodus bleiben ausschließlich während der Programmlaufzeit im Snapshot. RAM-Fenster zeigen „Stand der letzten erfolgreichen RAM-Erfassung“; das ist keine laufende Belegungs-/Hotplug-Prüfung. Kein lshw oder pkexec beim Öffnen und Beobachten.

F5 führt eine neue Bestandsaufnahme im vorgesehenen normalen beziehungsweise optional erweiterten Modus aus. Bestätigte vollständige RAM-Daten werden zusammen mit Zeitstempel und Modus atomar ersetzt. Eine unbekannte Bank, eine fehlende zuvor erfasste Steckplatzkennung oder eine fehlgeschlagene Abfrage gilt als eingeschränkte Aktualisierung: Die vorherigen bestätigten RAM-Daten bleiben unverändert mit ihrem ursprünglichen Zeitpunkt erhalten, erhalten einen deutlichen Altershinweis, und der Fehlschlag wird gemeldet. Ohne bisher bestätigte Erfassung bleiben fehlende Daten unbekannt. Nicht verfügbare Angaben werden nicht zu einer Leerbelegung umgedeutet.

Neue bestätigte Leerbelegung beziehungsweise ein anderes Modul setzt das alte Modul außer Kraft. Offene Fenster des bisherigen Moduls zeigen „Überholt“ und ihre historischen Daten; Fenster desselben Moduls übernehmen neue Felder, Modus und Zeitstempel gemeinsam. RAM-Exporte nennen Erfassungszeitpunkt, Aktualisierungsstatus und Modus; Seriennummern bleiben an die persönliche Exportauswahl gebunden. Beim Beenden wird der Sitzungssnapshot verworfen; es gibt keine neue Cachedatei. Monitor-/PCIe-Liveprüfungen bleiben erhalten. Unplausible RAM-Geschwindigkeiten werden weiterhin nicht repariert oder erfunden.

## RAM-Firmwaregeschwindigkeit (0.3.2)

Beim ausdrücklich gewählten erweiterten Start und F5 in diesem Modus wird auch `dmidecode --type 17` lesend erhöht ausgeführt. Normaler Start: ausschließlich unprivilegierte Abfrage. Detailklick und periodische Überwachung: weiterhin keinerlei RAM-/Firmwareabfrage. Die GUI bleibt beim normalen Benutzer. Zusätzliche Passwortbestätigung ist möglich; keine passwortfreie oder dauerhaft erhöhte Ausführung.

Die eindeutige, exakt übereinstimmende Steckplatzbezeichnung ordnet die Daten zu. „Configured Memory Speed“ erscheint als „Konfigurierte Datenrate (Firmware)“, „Speed“ getrennt als „Gemeldete Modulgeschwindigkeit (Firmware)“. Einheiten werden unverändert als MT/s beziehungsweise MHz behandelt, ohne Umrechnung oder Gleichsetzung. Die unbestätigte lshw-Taktangabe bleibt separat; kein Überlauf wird repariert. Das bereitgestellte Beispiel nennt für DIMMA2 und DIMMB2 jeweils zweimal 6000 MT/s; diese Werte sind nicht im Programm hinterlegt.

Quelle, Abfragemodus und tatsächlicher Firmware-Erfassungszeitpunkt stehen in Details und TXT-Bericht. Ein von dmidecode gemeldeter SMBIOS-Kompatibilitätshinweis wird mit verfügbaren Versionsangaben angezeigt, ohne pauschales Verwerfen aller Werte. Firmwareangaben sind keine laufende Taktmessung.

Fehlendes Werkzeug, abgelehnte/abgebrochene erweiterte Abfrage, Zeitüberschreitung, unvollständige Werte und widersprüchliche/mehrfache Steckplatzangaben besitzen getrennte Quellenstatus. Erfolgreiche lshw-Moduldaten bleiben erhalten. Nach einem Firmwarefehlschlag können vorher vollständig bestätigte Werte ausschließlich desselben Moduls weiterverwendet werden; sie tragen ausdrücklich den alten Firmwarezeitpunkt und den Hinweis „Ältere bestätigte Firmwareangaben“. Eine neue erfolgreiche lshw-Erfassung erhält ihren eigenen aktuellen Zeitpunkt. Bei Modulwechsel werden keine Firmwarewerte des Vorgängers übertragen. Sensible Seriennummern bleiben vom normalen Export ausgeschlossen. Keine neue dauerhafte Speicherung.


## Diagnose der erweiterten Abfrage (0.3.4)

Bei Fehlern zuerst Hilfe → Protokoll ansehen. Die Admin-Diagnose protokolliert Status, Fehlerstufe, Rückgabecode und gefilterte stderr-Fehlerkategorien, keine Hardware-Rohdaten oder Seriennummern. Unbekannte stderr-Inhalte werden nur als vorhanden gekennzeichnet. Einmalige Diagnose ohne GUI: `./start-admin.sh --diagnose-admin`. Sie fordert höchstens einmal Rechte an und gibt ausschließlich Diagnose und Quellenstatus aus. Bitte die Ausgabe bei erneutem Fehlschlag bereitstellen.

Ein reproduzierter Helfer-Absturz beim Python-Ende wurde behoben: Der Steuerthread verwendet jetzt ungepuffertes os.read statt einer blockierenden gepufferten stdin-Lesefunktion. Die Standardbibliothek wird beim tatsächlich gestarteten /usr/bin/python3 mit -I -S ermittelt. Die konkrete Ursache auf dem Benutzerrechner ist ohne dessen neues Diagnoseprotokoll weiterhin nicht bestätigt. Echter Passwortdialog und root-RAM-Erfassung bleiben manuell zu prüfen.


## RAM-Übersicht (0.3.5)

Belegte Steckplätze zeigen Hersteller, Modell, Kapazität und konfigurierte Firmware-Datenrate. Ohne gültige konfigurierte Datenrate steht Nicht ermittelbar; die gemeldete Modulgeschwindigkeit ersetzt sie nicht. Ältere bestätigte Firmwarewerte tragen Altershinweis und ursprünglichen Zeitpunkt. Unplausible lshw-Rohwerte erscheinen ausschließlich in den Details als verworfen. Die Firmwarewerte sind keine aktuelle Taktmessung. Export und GUI verwenden denselben RAM-Zeileninhalt. Der Ergebnisbereich und die lokale Hilfe zeigen das festgelegte Wolfskopf-mit-D-Bild als dezentes Wasserzeichen.


## Veröffentlichung 0.5.1

GitHub: https://github.com/Lehner-007/pcmonitor. DE/EN sind im Basispaket; acht weitere Sprachpakete mit Hilfe liegen getrennt unter sprachpakete. Diese zusätzlichen Übersetzungen wurden maschinell erstellt und benötigen muttersprachliche Prüfung. Das Benutzer-ZIP wird mit `python3 pcmonitor.py` gestartet; für eine erweiterte Erfassung `PCMONITOR_ADMIN_QUERY=1 python3 pcmonitor.py`. Die gesamte GUI nicht mit sudo starten. Im Quellordner bleiben .start.sh und start-admin.sh verfügbar. Veröffentlichung über den geprüften Versionstag und GitHub Actions; ZIP und SHA-256-Prüfsumme werden als Release-Anhänge bereitgestellt.

## DEB-Installation

Mit `sudo apt install ./pcmonitor_0.5.1_all.deb` installieren. Zwei Desktop- und Menü-Starter: pcmonitor ohne Rechteabfrage sowie pcmonitor – Administrator mit einmaliger erhöhter Hardwareabfrage. Die Oberfläche läuft als Benutzer. Bei normalem Entfernen werden eigene Einstellungen und verwaltete Starter bereinigt; Upgrades erhalten diese Daten.

## Version 0.5.4

Diese Version behebt bestätigte Probleme mit automatischen Updateprüfungen, unbekannten Laufwerkswerten, unbeschränkten Werkzeugausgaben und unbegrenzt wachsendem Ereignisverlauf. Die Prozessbereinigung beendet auch Nachkommen eines bereits beendeten Elternprozesses. Nichtblockierende Pipes verhindern unbegrenztes Warten auf geerbte Ausgabepipes; Zeitüberschreitung und Abbruch umfassen eine feste Bereinigungsfrist. Ereignisse zeigen ihren erfassten Zeitraum und ausgelassene ältere Einträge an. Paketdownloads werden vor Verwendung auf SHA-256, Paketkennung, Version und Architektur geprüft. Der Release enthält die geprüften Programmdateien und das installierbare DEB. Hardware- und Administratorabfragen auf dem Ziel-PC bleiben als separate manuelle Abnahme ausgewiesen.

Das DEB und seine SHA-256-Prüfsumme sind im GitHub-Release 0.5.4 verfügbar; `version.json` verweist auf diesen geprüften Release.
