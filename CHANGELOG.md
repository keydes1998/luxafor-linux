# Changelog

## 1.0.0 — 2026-10-19

Erste veröffentlichte Version.

- Luxafor Flag (Gen1 `04d2:bada`, Gen2/Microchip `04d8:f372`) über natives
  hidraw mit dokumentierten Protokollen (Farbe, Wave 1–5, Pattern 1–7, Strobe,
  Fade [Gen2], Off)
- Microsoft Teams-Präsenz-Sync (Graph, OAuth2/PKCE, Einmal-Anmeldung, Secret-Service-Tokens)
- Outlook-Kalenderberücksichtigung (Pufferzeiten, Konfliktregel, Datenschutzfilter)
- Regel-Engine (presence/calendar/schedule/idle/lock/webhook, Prioritäten), Profile
- Manuelle Statussteuerung mit Ablaufzeit, Statuskatalog
- REST-API (localhost standardmäßig, SSE-Live-Events), Webhook-Trigger
- PySide6-GUI (Dashboard/Geräte/Integrationen/Automatisierungen/Profile/Einstellungen/Diagnose),
  Tray, Einrichtungsassistent Microsoft, DE/EN, Dark/Light
- Desktop-Integration: udev (uaccess, beide Generationen), systemd-User-Service,
  .desktop, Autostart, Icons; install/uninstall; RPM-/DEB-Bau
- Simulation ohne Hardware, Diagnose mit bereinigtem Log-Export