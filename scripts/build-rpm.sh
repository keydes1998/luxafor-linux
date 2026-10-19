#!/usr/bin/env bash
# Baut ein RPM für Fedora. Benötigt: rpmbuild (sudo dnf install rpm-build)
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)"
DEST="~/rpmbuild"
mkdir -p "$DEST"/{SOURCES,SPECS,RPMS,SRPMS,BUILD}

# Quell-Archiv (ohne venv/tests)
TARBALL="luxafor-linux-${VERSION}.tar.gz"
tar czf "$DEST/SOURCES/$TARBALL" \
    --transform "s,^,luxafor-linux-${VERSION}/," \
    --exclude=.venv --exclude=.git --exclude=.pytest_cache \
    --exclude=src/luxafor.egg-info --exclude='**/__pycache__' \
    src pyproject.toml README.md LICENSE packaging scripts

cp packaging/rpm/luxafor.spec "$DEST/SPECS/"
rpmbuild -bb "$DEST/SPECS/luxafor.spec" --define "_topdir $(eval echo $DEST)"
echo "RPM unter $DEST/RPMS/$(arch)/ gebaut."