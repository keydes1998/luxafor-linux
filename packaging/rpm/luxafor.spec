# RPM spec für Fedora — baut mit scripts/build-rpm.sh
%global srcname luxafor-linux
%global _python_user_install 1

Name:           %{srcname}
Version:        1.0.0
Release:        1%{?dist}
Summary:        Luxafor LED Steuerung mit Microsoft Teams/Outlook-Integration
License:        MIT
URL:            https://example.invalid/luxafor-linux
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.11, python3-pip, python3-venv
Requires:       systemd
Requires:       libhidapi-hidraw0

%description
Moderne Linux-Alternative zum offiziellen Luxafor-Client:
- Direkte USB-HID-Steuerung von Luxafor Geräten (Flag)
- Microsoft Teams Präsenz-Synchronisierung (Entra ID + Graph, OAuth2/PKCE)
- Outlook-Kalenderberücksichtigung, Regel-Engine, Profile, Webhooks
- PySide6 GUI, Tray, systemd user service, lokale REST-API

%prep
%autosetup -n %{name}-%{version}

%build
# venv-basierte Installation im %install-Schritt

%install
mkdir -p %{buildroot}%{_prefix}/lib/luxafor/src
cp -r src/luxafor %{buildroot}%{_prefix}/lib/luxafor/src/
mkdir -p %{buildroot}%{_prefix}/lib/systemd/user
install -m 0644 packaging/systemd/luxafor-core.service %{buildroot}%{_prefix}/lib/systemd/user/luxafor-core.service
mkdir -p %{buildroot}%{_sysconfdir}/udev/rules.d
install -m 0644 packaging/udev/90-luxafor.rules %{buildroot}%{_sysconfdir}/udev/rules.d/90-luxafor.rules
mkdir -p %{buildroot}%{_datadir}/applications
install -m 0644 packaging/desktop/luxafor.desktop %{buildroot}%{_datadir}/applications/luxafor.desktop
cp -r packaging/icons/hicolor %{buildroot}%{_datadir}/icons/ || true
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/lx-core <<'EOS'
#!/usr/bin/env python3
import sys; sys.path.insert(0, "/usr/lib/luxafor/src")
from luxafor.core.app import run_core
run_core()
EOS
cat > %{buildroot}%{_bindir}/lx-gui <<'EOS'
#!/usr/bin/env python3
import sys; sys.path.insert(0, "/usr/lib/luxafor/src")
from luxafor.ui.main import main
main()
EOS
chmod +x %{buildroot}%{_bindir}/lx-core %{buildroot}%{_bindir}/lx-gui

%files
%{_bindir}/lx-core
%{_bindir}/lx-gui
%{_prefix}/lib/luxafor/src/luxafor
%{_prefix}/lib/systemd/user/luxafor-core.service
%{_sysconfdir}/udev/rules.d/90-luxafor.rules
%{_datadir}/applications/luxafor.desktop
%{_datadir}/icons/hicolor/*/apps/luxafor.png
%doc README.md LICENSE

%post
systemctl --user daemon-reload 2>/dev/null || true
udevadm control --reload-rules 2>/dev/null || true
cat <<'HINWEIS'
Luxafor installiert. Empfohlen:
  systemctl --user enable --now luxafor-core
  lx-gui
 Für Teams: Entra-ID-App-Registrierung, Client-ID unter Integrationen eintragen.
HINWEIS

%changelog
* Mon Oct 19 2026 Luxafor Linux Contributors <luxafor@localhost> - 1.0.0-1
- Erstveröffentlichung