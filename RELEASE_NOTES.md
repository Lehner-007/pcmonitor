pcmonitor 0.5.4

Behebt die Prozessbereinigung bei Zeitüberschreitung und Abbruch, auch wenn Nachkommen nach dem Ende des Hauptprozesses Ausgabepipes offen halten. Prozessausgaben werden nichtblockierend gelesen; die Bereinigungszeit ist begrenzt. Regressionstests decken geerbte Pipes und SIGTERM-ignorierende Nachkommen ab.
