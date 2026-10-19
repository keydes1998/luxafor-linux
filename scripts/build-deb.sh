#!/usr/bin/env bash
# Baut ein DEB für Ubuntu/Debian. Benötigt: dpkg-deb, python3-venv
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)"
PKG="luxafor-linux_${VERSION}_all"
TMP="$(mktemp -d)/$PKG"
trap 'rm -rf "$(dirname "$TMP")"' EXIT

install -d "$TMP/DEBIAN" "$TMP/usr/lib/python3/dist-packages" "$TMP/usr/bin"

# Quellen direkt installieren (System venv via python3 im Postinst)
cp -r src/luxafor "$TMP/usr/lib/python3/dist-packages/"
find "$TMP" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$TMP/DEBIAN/control" <<EOF
Package: luxafor-linux
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-venv, python3-pip, libhidapi-hidraw0 | libhidapi0
Maintainer: Luxafor Linux Contributors <luxafor@localhost>
Description: Luxafor LED Steuerung mit Microsoft Teams/Outlook Integration
 Moderne Linux-Alternative zum offiziellen Luxafor-Client: direkt USB-HID,
 Teams-Praesenz via Microsoft Graph, Outlook-Kalender, Regel-Engine, GUI, Tray.
EOF

cat > "$TMP/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
VENV=/usr/lib/luxafor/venv
if [ ! -x "$VENV/bin/pip" ]; then
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet hidapi msal aiohttp jeepney keyring cryptography PySide6
    "$VENV/bin/pip" install --quiet --no-deps /usr/lib/python3/dist-packages/luxafor-linux-*.whl 2>/dev/null || \
    "$VENV/bin/pip" install --quiet luxafor-linux || true
    # Falls das Pip-Paket nicht verfügbar ist: direkt aus dem installierten Quellcode laufen lassen
    if [ ! -x "$VENV/bin/lx-core" ]; then
        export PYTHONPATH=/usr/lib/python3/dist-packages
        cat > "$VENV/bin/lx-core" <<EOS
#!/usr/bin/env python3
import sys; sys.path.insert(0, "/usr/lib/python3/dist-packages")
from luxafor.core.app import run_core
run_core()
EOS
        cat > "$VENV/bin/lx-gui" <<EOS
#!/usr/bin/env python3
import sys; sys.path.insert(0, "/usr/lib/python3/dist-packages")
from luxafor.ui.main import main
main()
EOS
    fi
    chmod +x "$VENV/bin/lx-core" "$VENV/bin/lx-gui" 2>/dev/null || true
fi
ln -sf "$VENV/bin/lx-core" /usr/bin/lx-core
ln -sf "$VENV/bin/lx-gui" /usr/bin/lx-gui
install -m 0644 /usr/lib/python3/dist-packages/luxafor/packaging/90-luxafor.rules /etc/udev/rules.d/90-luxafor.rules 2>/dev/null || true
udevadm control --reload-rules 2>/dev/null || true
echo "luxafor-linux installiert: lx-gui starten. systemd: systemctl --user enable --now luxafor-core"
EOS
chmod +x "$TMP/DEBIAN/postinst"

# udev + systemd + desktop + icons
install -d "$TMP/usr/lib/python3/dist-packages/luxafor/packaging" "$TMP/usr/share/applications" "$TMP/usr/lib/systemd/user" "$TMP/etc/udev/rules.d"
cp packaging/udev/90-luxafor.rules "$TMP/etc/udev/rules.d/"
cp packaging/systemd/luxafor-core.service "$TMP/usr/lib/systemd/user/"
cp packaging/desktop/luxafor.desktop "$TMP/usr/share/applications/"
cp -r packaging/icons "$TMP/usr/share/icons/" 2>/dev/null || {
    install -d "$TMP/usr/share/icons/hicolor/{16x16,32x32,64x128,128x128}/apps"
    cp packaging/icons/hicolor/*/apps/luxafor.png "$TMP/usr/share/icons/hicolor/128x128/apps/luxafor.png"
}

mkdir -p dist
dpkg-deb --build --root-owner-group "$(dirname "$TMP")" "dist/$PKG.deb"
echo "DEB: dist/$PKG.deb"
echo "Hinweis: die DEB-Version baut ihr venv beim Installieren (Internet nötig)."