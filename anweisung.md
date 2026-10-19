# Projekt: Luxafor Linux Client – Moderne Alternative zur Windows-Software

Du bist ein erfahrener Senior Softwareentwickler mit Spezialisierung auf Linux-Desktop-Anwendungen, USB-HID-Kommunikation, Microsoft Graph API, Microsoft Teams und moderne Benutzeroberflächen.

Deine Aufgabe ist es, eine vollständige, produktionsfähige Linux-Anwendung zu entwickeln, welche die wesentlichen Funktionen des offiziellen Luxafor Windows Clients nachbildet und um zusätzliche Integrationen und Automatisierungsmöglichkeiten erweitert.

**WICHTIG: Ich möchte keine reine Demo oder einen funktionslosen UI-Prototyp, sondern eine tatsächlich nutzbare Anwendung mit funktionierender Hardware-Ansteuerung und Microsoft-365-Integration.**

## 1. Grundlegende Anforderungen

Die Anwendung soll hauptsächlich unter Fedora Linux mit GNOME und Wayland laufen, jedoch möglichst auch Ubuntu, Debian und andere Linux-Distributionen unterstützen.

Ziele:

- Eine moderne, übersichtliche Benutzeroberfläche
- Direkte Steuerung von Luxafor USB-Geräten
- Automatische Synchronisierung des Microsoft-Teams-Status
- Integration von Microsoft 365 und Outlook
- Manuelle Statussteuerung
- Individuelle Farben, Effekte und Automatisierungen
- Dauerhafter Betrieb im Hintergrund
- Automatischer Start nach dem Linux-Login
- Ressourcenverbrauch möglichst gering
- Keine Cloud-Anbindung außer den ausdrücklich aktivierten Integrationen
- Vollständige lokale Konfigurationsverwaltung

Die Anwendung soll kostenlos, ohne Luxafor-Cloud-Zwang und möglichst ohne zusätzliche Systemabhängigkeiten funktionieren.

## 2. Technologiestack

Bevorzugte Architektur:

**Backend:**
- Python 3.12+ 
- hidapi bzw. python-hid für die USB-HID-Kommunikation
- Microsoft Authentication Library (MSAL)
- Microsoft Graph API
- SQLite für lokale Einstellungen, Regeln und Ereignisse
- Asynchrone Hintergrundprozesse für Statusabfragen und Automatisierungen

**Frontend:**
- Bevorzugt PySide6 / Qt mit QML für eine moderne native Benutzeroberfläche
- Alternativ Tauri mit einem schlanken lokalen Backend, falls dies einen deutlichen Mehrwert bietet
- Moderne UI mit Dark Mode und Light Mode
- GNOME-kompatible Fenstergestaltung
- System-Tray-Unterstützung, soweit von der Desktopumgebung unterstützt

Vermeide Electron, sofern keine zwingenden Gründe dafür sprechen.

Trenne die Oberfläche, Hardwarekommunikation, Integrationen und Regelverarbeitung sauber voneinander.

Die Anwendung soll modular sein, damit später zusätzliche Integrationen ergänzt werden können.

## 3. Unterstützung der Luxafor-Geräte

Implementiere eine eigenständige Hardware-Abstraktionsschicht.

Die Anwendung soll angeschlossene Luxafor-Geräte automatisch erkennen und unterstützen, soweit deren USB-HID-Protokoll dokumentiert ist.

Primär soll Luxafor Flag unterstützt werden.

Weitere Modelle wie Luxafor Orb oder andere kompatible Produkte sollen über separate Gerätetreiber ergänzt werden können.

Funktionen:

- USB-Geräte automatisch erkennen
- Hersteller-ID und Produkt-ID auslesen
- Kompatible Geräte anzeigen
- Gerät verbinden und trennen
- Automatischer Reconnect bei USB-Unterbrechung
- Mehrere Geräte verwalten
- Farbe individuell pro Gerät setzen
- RGB-Farbwerte verwenden
- LEDs vollständig ausschalten
- Helligkeit einstellen, sofern vom Gerät unterstützt
- Verschiedene LED-Effekte verwenden
- LED-Zonen getrennt steuern, sofern unterstützt
- Gerätestatus anzeigen
- Testfunktion für die LED
- Fehler bei nicht unterstützten Befehlen verständlich anzeigen

Implementiere eine udev-Regel zur sicheren Gerätefreigabe ohne dauerhafte Root-Rechte.

Dokumentiere exakt, welche USB-Geräte unterstützt werden.

Erfinde keine USB-Kommandos oder Hardwarefähigkeiten. Verwende ausschließlich dokumentierte bzw. überprüfbare HID-Befehle.

Bei nicht vorhandener Hardware soll ein Simulationsmodus verfügbar sein.

## 4. Microsoft Teams – automatische Statussynchronisierung

Dies ist eine der wichtigsten Funktionen der gesamten Anwendung.

Ich möchte mich mit meinem Microsoft-365-Geschäftskonto anmelden können.

Verwende hierfür:

- Microsoft Entra ID
- OAuth 2.0 Authorization Code Flow mit PKCE oder einen geeigneten MSAL-Desktop-Flow
- Microsoft Graph API
- Delegierte Berechtigungen, insbesondere Presence.Read
- Sichere Tokenverwaltung
- Automatische Tokenaktualisierung

Implementiere einen Anmeldeassistenten:

1. Microsoft-365-Konto verbinden
2. Microsoft-Anmeldung durchführen
3. Berechtigungen prüfen
4. Verbindung testen
5. Teams-Anwesenheitsstatus auslesen
6. Automatische Synchronisierung aktivieren

Der Teams-Status soll den LED-Status steuern.

Standardzuordnung:

| Microsoft Teams | Luxafor |
|---|---|
| Available | Grün |
| Busy | Rot |
| DoNotDisturb | Dunkelrot |
| InAMeeting | Rot |
| InACall | Rot |
| Presenting | Rot blinkend |
| Away | Gelb |
| BeRightBack | Orange |
| Offline | LED aus |
| PresenceUnknown | Einstellbare Ersatzfarbe |

Verarbeite neben `availability` auch das Graph-Feld `activity`, um Besprechungen, Telefonate oder Präsentationen unterscheiden zu können.

Die Zuordnung der Microsoft-Statuswerte muss vollständig durch den Benutzer anpassbar sein.

Weitere Anforderungen:

- Automatische Aktualisierung der Anwesenheit
- Abfrageintervall einstellbar
- Möglichst schnelle Reaktion auf Statusänderungen
- Unterstützung dokumentierter Graph-Change-Notifications, sofern sinnvoll und zuverlässig umsetzbar
- Fehlerbehandlung bei API-Throttling
- Exponentielles Backoff bei Verbindungsfehlern
- Anzeige der letzten erfolgreichen Synchronisierung
- Darstellung des aktuellen Teams-Status in der Oberfläche
- Automatisches Wiederverbinden nach Netzwerkunterbrechungen

Wichtig:

Die Lösung muss unter Linux funktionieren und darf keine Windows-spezifischen Teams-Schnittstellen voraussetzen.

Microsoft Graph ist die primäre Informationsquelle.

Eine Benutzeranmeldung darf nicht durch einen dauerhaft gespeicherten Benutzernamen und ein Passwort simuliert werden.

Sollte eine Microsoft-365-Organisation die benötigten Berechtigungen nicht freigeben, muss die Anwendung dies erkennen und konkrete Hinweise für den Administrator anzeigen.

## 5. Microsoft Outlook und Kalender

Integriere optional den Microsoft-365-Kalender.

Funktionen:

- Kalender über Microsoft Graph verbinden
- Aktuelle und bevorstehende Termine erkennen
- Besprechungszeiten berücksichtigen
- Automatische Aktivierung von „Beschäftigt“
- Status bei Terminbeginn ändern
- Status nach Terminende zurücksetzen
- Pufferzeit vor und nach Besprechungen definieren
- Private Termine datensparsam behandeln
- Optional nur Verfügbarkeitsinformationen lesen

Beispiel:

Ein Termin beginnt um 10:00 Uhr und endet um 11:00 Uhr.

Um 09:55 Uhr kann die LED bereits auf Gelb wechseln.

Ab 10:00 Uhr leuchtet sie Rot.

Ab 11:00 Uhr wird wieder der Teams-Status übernommen.

Dabei soll der Benutzer selbst entscheiden können, ob Teams oder Outlook bei Konflikten Vorrang hat.

## 6. Manuelle Statussteuerung

Über die Oberfläche soll der Benutzer jederzeit einen manuellen Status setzen können.

Vordefinierte Status:

- Verfügbar
- Beschäftigt
- Nicht stören
- In Besprechung
- Pause
- Abwesend
- Fokuszeit
- Individueller Status

Jeder Status bekommt:

- Einen Namen
- Eine Farbe
- Optional einen Effekt
- Eine individuelle Priorität
- Optional eine automatische Ablaufzeit

Beispiel:

Ich setze meinen Status manuell auf „Nicht stören – 30 Minuten“.

Die Luxafor-LED wird Rot.

Nach 30 Minuten wird automatisch die Teams-Synchronisierung fortgesetzt.

Ergänze einen Button:

**Automatischen Status wiederherstellen**

Die manuelle Statusänderung soll standardmäßig nur das Luxafor-Gerät ändern, nicht den Microsoft-Teams-Status.

Eine spätere bidirektionale Synchronisierung darf nur mit gesonderter, expliziter Aktivierung und geeigneten Microsoft-Graph-Berechtigungen möglich sein.

## 7. Regel-Engine und Automatisierung

Entwickle eine flexible, erweiterbare Regel-Engine.

Der Benutzer soll ohne Programmierkenntnisse eigene Regeln definieren können.

Beispiele:

**Regel 1 – Teams**
Wenn Teams = Busy, dann LED Rot.

**Regel 2 – Meeting**
Wenn ein Outlook-Termin beginnt, dann LED Rot.

**Regel 3 – Bildschirm sperren**
Wenn der Linux-Bildschirm gesperrt wird, dann LED Gelb oder Aus.

**Regel 4 – Abwesenheit**
Wenn 10 Minuten keine Benutzeraktivität erkannt wird, dann LED Gelb.

**Regel 5 – Fokuszeit**
Wenn Fokusmodus aktiviert wird, dann LED Dunkelrot.

**Regel 6 – Feierabend**
Ab 18:00 Uhr LED ausschalten.

**Regel 7 – Manuelle Überschreibung**
Manuell gesetzter Status hat für eine definierte Zeit Vorrang.

Regeln sollen Prioritäten besitzen.

Empfohlene Standardpriorität:

1. Kritische Benachrichtigung
2. Manuelle Überschreibung
3. Aktives Teams-Telefonat oder Präsentation
4. Teams- oder Outlook-Besprechung
5. Fokusmodus
6. Normaler Teams-Status
7. Automatische Abwesenheit
8. Standardfarbe

Prioritäten müssen individuell anpassbar sein.

Verhindere, dass sich konkurrierende Regeln gegenseitig dauerhaft überschreiben.

Der aktive Status soll mit seiner auslösenden Regel sichtbar sein.

## 8. Moderne Benutzeroberfläche

Entwickle eine optisch hochwertige Anwendung.

Designrichtung:

- Modernes SaaS-Dashboard
- Dezente abgerundete Elemente
- Klare Typografie
- Übersichtliche Karten
- Dark Mode standardmäßig
- Optionale helle Darstellung
- Dezente Animationen
- Kompakte Navigation
- Kein überladenes Design

Hauptnavigation:

### Dashboard

Zeige:

- Aktueller Luxafor-Status
- Aktuelle LED-Farbe als Live-Vorschau
- Erkannte USB-Geräte
- Microsoft-Teams-Verbindungsstatus
- Aktueller Teams-Anwesenheitsstatus
- Nächster Outlook-Termin
- Aktive Automatisierung
- Schaltflächen zum schnellen Statuswechsel

### Geräte

- Luxafor-Geräteübersicht
- Geräteeinstellungen
- Farb- und Helligkeitssteuerung
- LED-Zonen
- Effekte
- Funktionstest

### Integrationen

- Microsoft Teams
- Microsoft Outlook
- Webhooks
- Später weitere Anwendungen

### Automatisierungen

- Regelübersicht
- Regeln erstellen
- Regeln bearbeiten
- Prioritäten definieren
- Zeitpläne
- Regelaktivität prüfen

### Profile

Verschiedene Profile wie:

- Büro
- Homeoffice
- Fokus
- Meeting
- Feierabend

Profile sollen unterschiedliche Farbzuordnungen und Regeln enthalten können.

### Einstellungen

- Anwendung mit Linux starten
- Minimiert starten
- Hintergrundbetrieb
- Synchronisierungsintervall
- Benachrichtigungen
- Designs
- Sprache Deutsch / Englisch
- Logging
- Diagnose
- Updates

## 9. System-Tray und Hintergrundbetrieb

Die Anwendung darf nicht beendet werden, sobald das Fenster geschlossen wird.

Implementiere:

- Hintergrundbetrieb
- Optionales Schließen in den System-Tray
- Tray-Menü mit aktuellem Status
- Schnellwechsel zwischen Verfügbar, Beschäftigt und Nicht stören
- Anwendung öffnen
- Synchronisierung pausieren
- LED ausschalten
- Anwendung vollständig beenden

Berücksichtige, dass GNOME unter Wayland nicht in jeder Konfiguration klassische Tray-Icons unterstützt.

Implementiere deshalb eine geeignete Alternative, beispielsweise einen Hintergrunddienst mit GUI-Steuerung oder eine optionale AppIndicator-Erweiterung.

Nutze einen systemd-User-Service für den zuverlässigen Hintergrundbetrieb.

## 10. Weitere Integrationen

Bereite ein Plugin-System für zusätzliche Integrationen vor.

Gewünschte Integrationen:

- Slack
- Zoom
- Google Calendar
- Lokale Anwendungen
- Home Assistant
- Eigene REST-API
- Webhooks

Die Integrationen sollen einzeln aktiviert und deaktiviert werden können.

### Lokale REST-API

Optional soll die Anwendung eine lokale API bereitstellen.

Beispiel:

POST /api/status

```json
{
  "status": "busy",
  "color": "#FF0000",
  "duration": 1800
}
```

Zusätzlich:

- GET /api/status
- GET /api/devices
- POST /api/device/color
- POST /api/device/off
- POST /api/profile/activate

Die API muss standardmäßig nur über localhost erreichbar sein.

Bei Aktivierung des Netzwerkzugriffs ist eine Authentifizierung verpflichtend.

## 11. Benachrichtigungen und LED-Effekte

Implementiere verschiedene LED-Effekte, sofern die Hardware diese unterstützt.

Beispiele:

- Dauerlicht
- Blinken
- Pulsieren
- Farbwechsel
- Kurzer Benachrichtigungsblitz

Anwendungsfälle:

- Besprechung beginnt
- Benutzer wird beschäftigt
- Kritische Webhook-Benachrichtigung
- Fokuszeit läuft ab

Effekte dürfen den eigentlichen Status nicht dauerhaft überschreiben.

Nach einem temporären Effekt soll die vorherige Farbe wiederhergestellt werden.

## 12. Sicherheit und Datenschutz

Da die Anwendung beruflich mit Microsoft 365 verwendet wird, gelten erhöhte Anforderungen.

Implementiere:

- Sichere OAuth-Anmeldung
- Minimale Graph-Berechtigungen
- Sichere Tokenablage, bevorzugt über Secret Service / GNOME Keyring
- Keine Klartextpasswörter
- Keine unnötige Speicherung von Kalenderinformationen
- Lokale Datenhaltung
- Keine Telemetrie
- Kein externes Tracking
- TLS-Zertifikate nicht ungeprüft akzeptieren
- Protokollierung ohne vertrauliche Zugriffstoken
- Sichere Berechtigungen für Konfigurationsdateien
- Fehler- und Diagnoseprotokolle

Die Anwendung muss auch offline für die manuelle Luxafor-Steuerung funktionieren.

## 13. Installation und Distribution

Das Projekt soll einfach auf Fedora installiert werden können.

Erstelle:

- Vollständigen Quellcode
- README.md
- Installationsskript
- Uninstall-Skript
- udev-Regeln
- systemd-User-Service
- Desktop-Datei für das Anwendungsmenü
- Paketierung als RPM für Fedora
- Möglichst zusätzlich DEB für Ubuntu und Debian

Die Installation soll benötigte Abhängigkeiten prüfen und erforderliche Systemänderungen transparent anzeigen.

Keine unnötigen Root-Rechte verwenden.

## 14. Diagnose und Fehlerbehandlung

Integriere einen Diagnosebereich.

Dieser soll prüfen:

- Ist ein Luxafor-Gerät angeschlossen?
- Wird es vom System erkannt?
- Stimmen die USB-Berechtigungen?
- Funktioniert die HID-Kommunikation?
- Besteht Internetverbindung?
- Ist Microsoft Graph erreichbar?
- Ist der Benutzer angemeldet?
- Sind die notwendigen Berechtigungen vorhanden?
- Wann wurde der Teams-Status zuletzt erfolgreich abgefragt?
- Welche Regel steuert aktuell die LED?
- Gibt es Fehler beim Hintergrunddienst?

Ermögliche den Export eines bereinigten Diagnoseprotokolls ohne Zugangsdaten.

## 15. Entwicklungsablauf

Gehe strukturiert und in sinnvollen Phasen vor.

**Phase 1 – Analyse**

Prüfe dokumentierte Luxafor-Protokolle, vorhandene Linux-Bibliotheken sowie die Microsoft-Graph-Schnittstellen.

Entscheide dich anschließend für den geeignetsten Technologiestack.

**Phase 2 – Funktionierender Hardware-Treiber**

Implementiere die Erkennung und Steuerung der Luxafor Flag.

Teste Farben, Ein/Aus und unterstützte LED-Effekte.

**Phase 3 – Benutzeroberfläche**

Entwickle Dashboard, Geräteeinstellungen und manuelle Statussteuerung.

**Phase 4 – Microsoft Teams**

Implementiere die Microsoft-365-Anmeldung und die tatsächliche Teams-Presence-Synchronisierung.

**Phase 5 – Outlook und Automatisierungen**

Integriere Kalender, Zeitpläne und Regel-Engine.

**Phase 6 – Hintergrundbetrieb**

Implementiere systemd-Integration, Desktop-Integration und Tray-Funktionalität.

**Phase 7 – Release**

Erstelle Installationspakete, Dokumentation und automatische Tests.

## 16. Wichtige Entwicklungsregeln

- Schreibe wartbaren, modularen und gut dokumentierten Code.
- Nutze echte Schnittstellen und keine vorgetäuschten Statusdaten.
- Erfinde keine API-Endpunkte.
- Implementiere Fehlerbehandlung konsequent.
- Erstelle Tests für Hardwareabstraktion, Statusregeln und Graph-Integration.
- Verwende Mock-Geräte nur für Tests und den expliziten Simulationsmodus.
- Erhalte bestehende funktionierende Features bei jeder Weiterentwicklung.
- Vermeide unnötige externe Dienste.
- Beachte aktuelle Best Practices für Linux und Microsoft Graph.
- Gestalte die Oberfläche professionell und intuitiv.
- Implementiere alle Kernfunktionen tatsächlich, nicht nur die dazugehörigen Buttons.

## 17. Erwartetes Ergebnis

Am Ende möchte ich eine installierbare Linux-Anwendung, mit der ich:

1. Mein Luxafor-Gerät anstecken kann.
2. Das Gerät automatisch erkannt wird.
3. Farben und Effekte manuell steuern kann.
4. Mich mit meinem Microsoft-365-Konto anmelden kann.
5. Meinen Microsoft-Teams-Status automatisch auf der LED anzeigen kann.
6. Kalendertermine berücksichtigen kann.
7. Individuelle Regeln und Statusprofile erstellen kann.
8. Die Anwendung dauerhaft im Hintergrund betreiben kann.
9. Alle Funktionen über eine moderne Benutzeroberfläche verwalten kann.

Beginne mit einer kurzen technischen Analyse und einer konkreten Projektstruktur.

Starte anschließend direkt mit der tatsächlichen Implementierung.

Arbeite selbstständig und frage nur nach Informationen, die technisch zwingend notwendig sind, beispielsweise der verwendeten Luxafor-Modellvariante oder Microsoft-Entra-Konfigurationsdaten.

Nach jeder Phase soll das Projekt ausführbar bleiben und vorhandene Funktionen dürfen nicht beschädigt werden.
