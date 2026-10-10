# Änderungen

## 0.4.0 – 10.10.2026

GitHub-Veröffentlichungsablauf mit geprüftem Versionstag, Benutzer-ZIP und Prüfsumme. Paketierung ohne Entwicklungsdateien. GitHub-Adressen für Sprachpakete und Version hinterlegt; acht zusätzliche Sprachen mit Hilfe separat bereitgestellt (maschinell übersetzt, muttersprachliche Prüfung offen).

## 0.3.6 – 10.10.2026

Festgelegtes Wolfskopf-mit-D-Wasserzeichen in Ergebnisbereich, lokaler Hilfe und HTML-Bericht verwendet. Separate Ressource und Projektangabe, unabhängig vom Programmsymbol.

## 0.3.5 – 10.10.2026

RAM-Übersicht auf Hersteller/Modell/Kapazität und konfigurierte Firmware-Datenrate begrenzt; verworfene lshw-Rohwerte nur in Details. Fehlende/ältere Daten gekennzeichnet. Wasserzeichen im pcmonitor-Ergebnisbereich wiederhergestellt und in lokaler Hilfe ergänzt.

## 0.3.4 – 10.10.2026

Reproduzierten Helfer-Absturz beim Interpreter-Ende durch ungepufferten Abbruchkanal behoben. Diagnose unterscheidet Prozessstart, Prozessende, JSON und Schema mit Rückgabecode und datensparsamen stderr-Kategorien. Neue CLI --diagnose-admin. Standardbibliothek stammt vom tatsächlich verwendeten isolierten System-Python. 63 Tests; echter Benutzerrechner-Test offen.

## 0.3.3 – 10.10.2026

Doppelte Adminanforderung behoben: ein isolierter fester Helfer für lshw und dmidecode, getrennte Quellenstatus und Zeiten, unprivilegierte GUI und Rückfallerfassung. Abbruchkanal mit Prozessgruppenbereinigung, Zeitlimits, Erfassungssperre und Erhaltung älterer RAM-Daten. DE/EN-Hilfe aktualisiert. Echter Mint-Passwortdialog bleibt manuell zu prüfen.

## 0.3.2 – 10.10.2026

Erweiterte Bestandsaufnahme liest auch dmidecode --type 17 erhöht, GUI bleibt unprivilegiert. Konfigurierte und gemeldete Firmwaregeschwindigkeit getrennt, exakte Steckplatzzuordnung, Quellenzeit/Modus und SMBIOS-Hinweis. Einzelne Fehlerstatus und Erhaltung bestätigter älterer Firmwarewerte desselben Moduls. Admin-Tests ohne Abhängigkeit von installierten Werkzeugdateien, echte Ausgabe anonymisiert als Fixture.

## 0.3.1 – 10.10.2026

RAM-Details ausschließlich aus bestätigtem Sitzungssnapshot, ohne neue lshw-/pkexec-Abfrage beim Öffnen oder Beobachten. Erfassungszeit, Modus und Altershinweis in Oberfläche/Export; bestätigte Daten bei eingeschränkter Aktualisierung erhalten, erfolgreiche neue Generation atomar übernehmen und offene Fenster aktualisieren/als überholt markieren. Keine Cachedatei. Monitor-/PCIe-Prüfungen erhalten.

## 0.3.0 – 10.10.2026

Gerätedetails nur für nachweislich belegte, zugeordnete Anschlüsse/Steckplätze. Stabile Kennungen, Live-Prüfung ohne Rechteerhöhung, veraltete Ansichten nach Entfernung und gestoppte Detailabfragen. Monitor-EDID und getrennte aktive/unterstützte Modi, RAM-/PCIe-Details, Seriennummern nur im persönlichen Export. DE/EN-Hilfe ergänzt. 34 Unit-/Regressionstests sowie GTK-Detailtests in Hell/Dunkel bestanden; echte Hardwarekontrolle offen.

## 0.2.1 – 10.10.2026

Nachprüfung: LAN-carrier-Ereignisse vom Betriebszustand getrennt, verfügbare Sensormodelle ergänzt, Komponenten ohne anwendbare Belegung bei Filtern erhalten. Datenschutzgrenzen in DE/EN-Hilfe erläutert. 24 Regressionstests und GUI-Smoke-Test bestanden; Prüfung auf physischem Ziel-PC offen.

## 0.2.0 – 10.10.2026

Hardwarequellen und Zuordnung nach Quellcodeprüfung korrigiert: konservative RAM-Einheiten/Plausibilität, eindeutige EDID-Monitorzuordnung, NVIDIA-VRAM über PCI-Adresse, Gerätearten statt vorgetäuschter Buchsenbelegung, LAN/WLAN-Daten, BlueZ-Endgeräte und Audio-Standardgeräte, eindeutige Sensorpfade, vorhandene/Online-CPUs, Rückgabestatus der Virtualisierungsabfrage und Datenschutz für zusätzliche Quellen/Ereignisse. Admin-Starter bleibt auf lshw begrenzt. 21 Regressionstests und GUI-Prüfung; physische Hardwareprüfung offen.

## 0.1.0 – 10.10.2026

Erste Bestandsaufnahme mit 16 Bereichen, vorhandenen 3D-Bildern, TXT-Export und optionalem Admin-Starter für die lesende lshw-Abfrage.
