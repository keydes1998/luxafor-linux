# Luxafor Linux

Moderne Linux-Alternative zum offiziellen Luxafor-Client: direkte USB-Steuerung von
Luxafor-Geräten, automatische **Microsoft Teams**-Status-Synchronisierung
(Entra ID / Graph), **Outlook**-Kalenderberücksichtigung, Regel-Engine, Profile,
Webhooks, lokale REST-API, Tray und Hintergrundbetrieb über einen systemd-User-Service.

> Vollständig lokal. Keine Cloud-Anbindung außer den von dir aktivierten
> Microsoft-Integrationen. Keine Telemetrie.

---

## Architektur

```
┌──────────────────────────────┐        ┌────────────────────────────┐
│  lx-gui (PySide6, Tray)      │  REST  │  lx-core (asyncio daemon)  │
│  Dashboard / Geräte / …      │◀──────▶│  ├─ Hardware (HID)         │
└──────────────────────────────┘ SSE    │  ├─ State-Engine (Prio)    │
        systemd --user: luxafor-core    │  ├─ Regel-Engine           │
        (Hintergrundbetrieb)            │  ├─ MS Graph (Teams/Outlook)│
                                        │  ├─ Webhooks / Idle/Lock   │
                                        │  └─ REST API 127.0.0.1     │
                                        └────────────────────────────┘
```

- **`lx-core`** besitzt Hardware, Integrationen, Regeln. Läuft als systemd-User-Service
  weiter, auch wenn die GUI geschlossen wird.
- **`lx-gui`** ist ein dünner REST-Client inkl. Tray — Startet den Kern automatisch,
  falls er fehlt.

## Unterstützte Hardware

| Gerät | USB-ID (VID:PID) | Status | Funktionen |
|---|---|---|---|
| **Luxafor Flag (Gen1)** | `04d2:bada` | ✅ verifiziert | Farbe (alle/zonen), Wave 1–5, Pattern 1–7, Strobe, Aus |
| **Luxafor Flag (Gen2, Microchip)** | `04d8:f372` | ✅ erkannt (Produktstring „LUXAFOR FLAG") | Protokoll identisch dokumentiert: gleiche Befehle; Verifikation mit `scripts/probe_flag_protocol.py` |
| Andere Modelle („Luxafor"-Produktstring) | variiert | ⚠️ best effort mit Flag-Treiber | siehe Diagnose |

> Erkannt wird über **VID `04d2`** **oder** **`04d8:f372`** **oder** HID-Produktstring
> mit „Luxafor" — die Gen2-Hardware meldet sich mit Microchip-VID (`04d8`).

**Hinweis zum dokumentierten Flag-Protokoll:** Es enthält **keinen Helligkeitsbefehl**.
Die Helligkeit wird in der App per Software-Dämpfung (10–100 %) umgesetzt. Für
weitere Geräte (Orb etc.) lässt sich der Treiber in `src/luxafor/hardware/`
erweitern.

### udev-Regel

`/etc/udev/rules.d/90-luxafor.rules` setzt `TAG+="uaccess"` — der angemeldete
Desktop-Benutzer darf das HID-Gerät direkt öffnen, **ohne Root und ohne
Gruppenänderung**.

## Installation (Fedora, GNOME/KDE, Ubuntu, Debian)

```bash
git clone <repo> luxafor && cd luxafor
./scripts/install.sh
```

Das Skript:
1. prüft Python ≥ 3.11, legt `~/.local/share/luxafor/venv` an und installiert alle Abhängigkeiten,
2. installiert die **udev-Regel** (einmalig `sudo`),
3. aktiviert den **systemd-User-Service** `luxafor-core`,
4. installiert `.desktop`-Eintrag, Icons und Desktop-Autostart.

Deinstallation: `./scripts/uninstall.sh`

Für Distributionen:
- **RPM:** `./scripts/build-rpm.sh` (benötigt `dnf install rpm-build`)
- **DEB:** `./scripts/build-deb.sh`

## Erste Schritte

1. `lx-gui` starten (oder Desktop-Menü → Luxafor). Der Kern startet automatisch.
2. **Ohne Hardware** läuft der Simulator (`Einstellungen → Simulationsmodus`).
3. Manuelle Steuerung: Dashboard → Schnellstatus, Geräte-Seite (Farbe, Zonen, Effekte),
   oder CLI:

```bash
python -m luxafor status
python -m luxafor color #FF0000 --led front
python -m luxafor set "Nicht stören" --duration 30   # 30 Minuten
python -m luxafor restore
python -m luxafor diagnose
```

## Microsoft Teams synchronisieren (Entra ID)

Die Anwendung nutzt den **Microsoft Graph**-Endpunkt `/me/presence` mit delegierten
Berechtigungen und OAuth 2.0 Authorization-Code-Flow **mit PKCE** (Loopback-Redirect).
Token landen im **Secret Service / GNOME Keyring** (Fallback: verschlüsselte Datei,
chmod 0600). Keine Passwörter.

**Einmalige Vorbereitung im Entra-Admin-Center (App-Registrierung):**

1. *Neue Registrierung*: Name z. B. „Luxafor Linux“.
2. Plattform **Mobilgerät und Desktop** hinzufügen, Redirect-URI **`http://localhost`**.
3. API-Berechtigungen (delegiert): `User.Read`, `Presence.Read`, optional `Calendars.Read`.
   ggf. Admin-Zustimmung erteilen lassen, falls der Tenant Apps einschränkt.
4. **Client-ID (Application ID)** in der GUI unter *Integrationen → Microsoft Teams* eintragen → *Speichern* → *Anmelden*.

Kann die Organisation `Presence.Read` nicht freigeben, zeigt die Anwendung in der
Diagnose und bei der Anmeldung konkrete Hinweise für den Administrator
(fehlende Admin-Zustimmung, Redirect-URI-Konfiguration).

**Status-Zuordnung (anpassbar über Regel-Engine):**

| Microsoft Teams | Luxafor |
|---|---|
| Available | Grün |
| Busy / InAMeeting / InACall | Rot |
| Presenting | Rot blinkend (Strobe) |
| DoNotDisturb | Dunkelrot |
| Away | Gelb |
| BeRightBack | Orange |
| Offline | LED aus |
| PresenceUnknown | Konfigurierbare Ersatzfarbe |

Wird neben `availability` auch das Graph-Feld `activity` ausgewertet
(Anruf/Präsentation erzeugen eigene Regeln mit höherer Priorität).

## Outlook / Kalender

- KalenderView-Abfrage der nächsten Stunden; Termine mit `showAs ≠ free` sind „beschäftigt“.
- **Pufferzeiten** vor/nach Terminen konfigurierbar (z. B. 09:55 gelb ab 5 Min Vorlauf,
  10:00–11:00 rot, danach Teams-Status).
- Private Termine werden datensparsam als „Termin (privat)“ behandelt (Schalter).
- Konfliktregel: Teams wins / Kalender wins / Kalender während Termin, danach Teams.

## Regel-Engine

Regeln mit Priorität (0–100), Typen: `presence`, `calendar`, `schedule`, `idle`,
`lock`, `webhook`. Standard-Reihenfolge (anpassbar):

`95 Kritisch (Webhook) · 90 Manuell · 80 Anruf/Präsentation · 70 Besprechung ·
60 Fokus · 40 Teams-Präsenz · 30 Abwesenheit · 20 Zeitplan · 10 Standardfarbe`

Konkurrierende Regeln überschreiben sich nicht dauerhaft: Die State-Engine
wählt immer den **höchsten gültigen Kandidaten**; ablaufende Kandidaten
(Manual-Timeout, Meeting-Ende, Webhook-Dauer) geben automatisch wieder frei.
Der aktive Status zeigt in der GUI Ursprung und Regel.

## REST-API (Standard: 127.0.0.1:17800)

```http
GET  /api/status
POST /api/status            {"status":"Beschäftigt" | …, "color":"#FF0000", "duration":1800}
POST /api/status/restore
GET  /api/devices
POST /api/device/color      {"led":"front","color":"#FF0000","device":"flag:…"}
POST /api/device/off
POST /api/device/effect     {"effect":"strobe:4","color":"#00FF00"}
POST /api/device/flash      {"color":"#FF2200","duration":3}
POST /api/profile/activate  {"id":1}
GET  /api/events            (SSE Live-Stream)
GET  /api/diagnostics
GET/PUT  /api/settings      GET/POST/PUT/DELETE /api/rules, /api/profiles, /api/statuses, /api/webhooks
```

- Bindet standardmäßig nur an **localhost**; GUI, CLI und Skripte sprechen ihn direkt an.
- **Netzwerkfreigabe (LAN)** nur nach expliziter Aktivierung; dann ist ein
  Bearer-Token verpflichtend (`api.expose_lan` + erzeugtes `api.lan_auth_token`).

Webhook-Trigger: `POST /api/webhook/trigger/<token>` setzt ein temporären
LED-Zustand (Name/Token/Farbe/Dauer konfigurierbar).

## Hintergrundbetrieb

- systemd-User-Service `luxafor-core` (`systemctl --user status luxafor-core`)

**Einmal-Anmeldung (wie in der Windows-App):** Nach der einmaligen Einrichtung
(Einrichtungsassistent in *Integrationen → Microsoft Teams*, ~5 min) öffnet
**„Anmelden“** direkt den Microsoft-Browser-Dialog; die App prüft selbst die
Berechtigungen und aktiviert die Synchronisierung — ohne weitere Klicks.
Refresh-Tokens liegen im System-Keyring und werden automatisch erneuert,
du meldest dich nie wieder manuell an.
- GUI schließen → läuft im Tray weiter (Abschaltbar); Tray-Menü: Schnellstatus,
  Pause, LED aus, Beenden
- Desktop-Autostart; Option „minimiert starten“
- GNOME/Wayland-Hinweis: Tray-Icons brauchen die *AppIndicator*-Extension — der
  Hintergrunddienst läuft unabhängig davon weiter.

## Effekte

Dokumentierte Flag-Effekte: `solid`, `strobe` (Speed 0–255), `wave` (1–5),
`pattern` (1–7, firmwareseitig), `off`. Temporäre Effekte (Blitz) stellen die
vorige Farbe automatisch wieder her.

## Sicherheit & Datenschutz

- OAuth2/PKCE, minimale Scopes, Token im Secret Service (Fallback verschlüsselt, 0600)
- Keine Telemetrie, kein Tracking; Logs filtern Token automatisch heraus
- `logs/export` liefert ein bereinigtes Diagnose-JSON (ohne Tokens) — GUI: Diagnose → Exportieren
- Konfigurationsverzeichnisse mit 0700

## Diagnose

GUI: **Diagnose** (Gerät? HID-Rechte? Internet/Graph? Anmeldung? letzte Sync?
aktive Regel?) + Protokollansicht + bereinigter Export. CLI: `python -m luxafor diagnose`.

## Tests

```bash
./.venv/bin/python -m pytest tests/ -q
```

Ohne Hardware: Simulator aktiviert sich automatisch (`hardware.simulator=auto`);
Protokolltests prüfen die dokumentierten HID-Befehle gegen Encoder und Simulator.

## Projektstruktur

```
src/luxafor/
├── core/       Config, SQLite, Logging, Event-Bus, DeviceManager, State-Engine
├── hardware/   Flag-HID-Treiber, Simulator, Discovery (04d2:bada)
├── rules/      Regel-Modelle + Engine
├── integrations/ MSAL-Auth, Graph-Client, Presence, Kalender, Webhooks, Idle/Lock
├── api/        REST-Server (aiohttp, SSE)
├── cli.py      CLI (core, status, color, set, restore, diagnose …)
└── ui/         PySide6-GUI (Dashboard, Geräte, Integrationen, …), Tray
packaging/      udev · systemd · desktop · icons · RPM-Spec
scripts/        install.sh · uninstall.sh · build-rpm.sh · build-deb.sh
tests/          Protokoll, State-Engine, Regeln, API, Graph, DeviceManager
```

## Lizenz & Marken

- Projekt-Lizenz: **MIT** (siehe `LICENSE`)
- Abhängigkeiten: `PySide6` steht unter LGPLv3 (dynamische Nutzung; Nutzer
  können die Bibliothek ersetzen — dadurch mit MIT kompatibel), alle übrigen
  Laufzeit-Abhängigkeiten sind liberal lizenziert (MIT/BSD/Apache).
- *Luxafor* ist eine Marke von Luxafor (luxafor.com); dieses Projekt ist ein
  unabhängiger, inoffizieller Client — keine Affiliation, keine Endorsement.
- *Microsoft*, *Microsoft Teams*, *Outlook*, *Microsoft Entra ID* und
  *Microsoft Graph* sind Marken der Microsoft-Gruppe. Die Integration nutzt
  ausschließlich dokumentierte, delegierte Graph-Endpunkte.
## Fehlerbehebung: Flag leuchtet nicht

1. `luxafor diagnose` ausführen (GUI-Seite „Diagnose“ zeigt dasselbe).
2. Prüfen, dass der Kern das Gerät **erkennt**: Geräte-Seite in der GUI —
   steht dort ein Eintrag „geschlossen“ mit Fehler, fehlen die Rechte:
   `sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw`
   oder den Stick einmal ab-/anstecken, danach `luxafor diagnose` erneut.
3. Falls nur ein „Simulator“ in der Geräteliste steht, hat hidapi kein Gerät
   gefunden (anderes Modell? prüfe `lsusb | grep 04d2`).
4. Service neu laden: `systemctl --user restart luxafor-core`
5. Live-Log: `journalctl --user -u luxafor-core -f`
