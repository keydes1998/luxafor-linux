#!/usr/bin/env bash
# Luxafor Linux – Installation (User-Installation ohne Root, außer: udev-Regel)
set -euo pipefail
cd "$(dirname "$0")/.."

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "  $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

# ---------------------------------------------------------------------------
echo "== Luxafor Linux Installation =="

# 1. Voraussetzungen -----------------------------------------------------------
PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null; then
  err "python3 nicht gefunden. Bitte installieren: sudo dnf install python3"
  exit 1
fi
ver=$("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
ok "Python $ver gefunden"
major=$(echo "$ver" | cut -d. -f1)
if [ "$major" -lt 3 ]; then err "Python 3.x benötigt"; exit 1; fi

if ! command -v systemctl >/dev/null; then
  warn "systemd nicht gefunden – Hintergrunddienst wird eingerichtet, aber ggf. nicht verfügbar"
fi

# 2. virtuelle Umgebung anlegen ------------------------------------------------
VENV="$HOME/.local/share/luxafor/venv"
echo "== Erzeuge virtuelle Umgebung ($VENV) ..."
"$PY" -m venv "$VENV"
ok "venv erstellt"

echo "== Installiere Python-Abhängigkeiten (das dauert ein paar Minuten) ..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet .
ok "Paket luxafor-linux installiert"

# Wrapper-Verknüpfungen --------------------------------------------------------
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
ln -sf "$VENV/bin/lx-core" "$BIN/lx-core"
ln -sf "$VENV/bin/lx-gui"  "$BIN/lx-gui"
ln -sf "$VENV/bin/luxafor" "$BIN/luxafor" 2>/dev/null || warn "luxafor-CLI fehlt (Paketversion älter?) – nutze: $VENV/bin/python -m luxafor …"
ok "Kommandos lx-core / lx-gui / luxafor in $BIN"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) warn "$BIN ist nicht im PATH – ggf. profile ergänzen: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# 3. udev-Regel (benötigt einmalig Root) -----------------------------------------
RULE_SRC="packaging/udev/90-luxafor.rules"
RULE_DST="/etc/udev/rules.d/90-luxafor.rules"
pkill -f lx-core >/dev/null 2>&1 || true
pkill -f "python -m luxafor core" >/dev/null 2>&1 || true

# udev-Regel IMMER neu installieren (kein cmp-Skip – Versionen können sich ändern)
echo "== udev-Regel wird installiert/aktualisiert (sudo wird einmalig benötigt) =="
sudo install -m 0644 "$RULE_SRC" "$RULE_DST" \
  && ok "udev-Regel: $RULE_DST" \
  || warn "udev-Regel NICHT installiert – ohne Root wird kein Gerätezugriff möglich sein"
if command -v udevadm >/dev/null; then
  sudo udevadm control --reload-rules 2>/dev/null || true
  # auf ALLE bereits angeschlossenen Geräte anwenden (auch nach Reboot wirksam)
  sudo udevadm trigger --subsystem-match=hidraw 2>/dev/null || true
  sudo udevadm settle 2>/dev/null || true
  ok "udev-Regeln angewandt (trigger/settle)"
fi

# 4. systemd-User-Unit (Hintergrundbetrieb) ----------------------------------------
if command -v systemctl >/dev/null; then
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  sed "s|%h/.local/share/luxafor/venv|$VENV|" packaging/systemd/luxafor-core.service > "$UNIT_DIR/luxafor-core.service"
  systemctl --user daemon-reload
  systemctl --user enable --now luxafor-core.service >/dev/null 2>&1 || systemctl --user enable --now luxafor-core.service
  ok "systemd-User-Service aktiv (luxafor-core)"
  systemctl --user restart luxafor-core.service 2>/dev/null || true
  if loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q "=no"; then
    warn "Linger ist deaktiviert: Der Dienst startet erst nach dem Login (normal für Desktop-Systeme)."
  fi
fi

# 5. Desktop-Eintrag + Icons ------------------------------------------------------
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"
sed "s|Exec=lx-gui|Exec=$BIN/lx-gui|" packaging/desktop/luxafor.desktop > "$APP_DIR/luxafor.desktop"
ok "Desktop-Eintrag: $APP_DIR/luxafor.desktop"

ICON_BASE="$HOME/.local/share/icons/hicolor"
for size in 16 24 32 48 64 128; do
  dir="$ICON_BASE/${size}x${size}/apps"
  mkdir -p "$dir"
  cp "packaging/icons/hicolor/${size}x${size}/apps/luxafor.png" "$dir/"
done
command -v update-desktop-database >/dev/null && update-desktop-database "$APP_DIR" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f "$ICON_BASE" 2>/dev/null || true
ok "Icons installiert"

# 6. Autostart-Datei (GUI startet mit dem Desktop) ----------------------------------
AUTOSTART="$HOME/.config/autostart"
mkdir -p "$AUTOSTART"
sed "s|Exec=lx-gui|Exec=$BIN/lx-gui|" packaging/desktop/luxafor.desktop > "$AUTOSTART/luxafor-gui.desktop"
ok "Desktop-Autostart eingerichtet"

# 7. Abschluss ---------------------------------------------------------------------
echo
ok "Installation abgeschlossen."
echo
info "Wichtig für Microsoft-365-Integration (Teams):"
info "  1. Entra ID → App-Registrierung anlegen (Web oder Mobil/Desktop),"
info "     Redirect-URI 'http://localhost' (Plattform: Mobilgerät und Desktop),"
info "     delegierte Berechtigungen: User.Read, Presence.Read, Calendars.Read."
info "  2. Client-ID in der App eintragen: Integrationen → Microsoft Teams → Client-ID"
info     "     (oder Setting ms.client_id via API/CLI), dann 'Anmelden'."
echo
info "Start: lx-gui   |   Status: luxafor status   Test: luxafor diagnose"
info "Falls der Luxafor-Stick schon vor der Installation steckte:"
info "  Stick einmal ab- und wieder anstecken, danach prüfen: luxafor diagnose"
info "Logs:  ~/.local/state/luxafor/luxafor.log"
echo "Fedora-spezifisch: sudo dnf install hidapi (Bibliothek ist via pip installiert)"