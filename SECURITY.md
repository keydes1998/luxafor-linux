# Security Policy

## Einen Fehler melden

Bitte keine öffentlichen Issues für sicherheitsrelevante Funde — melde dich
über ein privatesIssue-Etikett, ein Mail-Drop oder GitHub-Security-Advisories:
https://github.com/keydes1998/luxafor-linux/security/advisories/new

## Umgang mit Zugangsdaten (Design-Grundsätze)

- Microsoft-Tokens liegen bevorzugt im **Secret Service** (GNOME Keyring /
  KDE Wallet). Fallback: Fernet-verschlüsselte Datei, chmod 0600,
  in `~/.local/state/luxafor/` (Dokumentation: diese Variante ist eine
  Verschleierung, kein Schutz gegen physischen Datenträgerzugriff).
- Die lokale REST-API bindet standardmäßig an **127.0.0.1**. LAN-Freigabe
  erfordert `api.expose_lan=true` **und** ein Bearer-Token.
- Webhooks werden per einzigartigem Token authentifiziert; URL-Parameter
  tauchen ggf. in Proxy-Logs auf.
- Logs redaktieren Tokens/Zugriffsköpfe automatisch
  (`luxafor.core.logging_setup.RedactingFilter`); der Diagnose-Export ist
  bereinigt.
- Keine Telemetrie, kein externes Tracking.

## Bekannte Grenzen

- `scripts/probe_flag_protocol.py` schreibt direkt auf `/dev/hidraw*` — reines
  LED-Kontrollgerät, keine Eingabegeräte-Angriffsfläche.
- Der systemd-User-Service läuft gehärtet (`NoNewPrivileges`, `PrivateTmp`,
  `ProtectSystem=full`, `ProtectHome=read-only` mit Ausnahmen).