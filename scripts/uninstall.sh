#!/usr/bin/env bash
# Luxafor Linux – Deinstallation (alles benutzerbezogen; udev-Regel per sudo)
set -euo pipefail

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

echo "== Luxafor Linux – Deinstallation =="

# systemd stoppen + entfernen
systemctl --user disable --now luxafor-core.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/luxafor-core.service"
systemctl --user daemon-reload 2>/dev/null || true
ok "systemd-User-Service entfernt"

# Autostart + Desktop-Eintrag
rm -f "$HOME/.config/autostart/luxafor-gui.desktop"
rm -f "$HOME/.local/share/applications/luxafor.desktop"
ok "Desktop-Einträge entfernt"

# Icons
rm -rf "$HOME/.local/share/icons/hicolor/16x16/apps/luxafor.png" \
       "$HOME/.local/share/icons/hicolor/24x24/apps/luxafor.png" \
       "$HOME/.local/share/icons/hicolor/32x32/apps/luxafor.png" \
       "$HOME/.local/share/icons/hicolor/48x48/apps/luxafor.png" \
       "$HOME/.local/share/icons/hicolor/64x64/apps/luxafor.png" \
       "$HOME/.local/share/icons/hicolor/128x128/apps/luxafor.png"

# Verknüpfungen + venv
rm -f "$HOME/.local/bin/lx-core" "$HOME/.local/bin/lx-gui"
rm -rf "$HOME/.local/share/luxafor/venv"
ok "Programmdateien entfernt"

warn "Konfiguration/State bleibt erhalten:"
echo "  ~/.config/luxafor          (Einstellungen, Endpoint)"
echo "  ~/.local/state/luxafor     (Datenbank, Logs, Token)"
echo "Entfernen mit: rm -rf ~/.config/luxafor ~/.local/state/luxafor"

echo
warn "udev-Regel (optional, braucht sudo):"
echo "  sudo rm -f /etc/udev/rules.d/90-luxafor.rules && sudo udevadm control --reload-rules"