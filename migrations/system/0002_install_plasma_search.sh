#!/usr/bin/env bash
# desktops: plasma
# Module 07 refreshes existing programs, but cannot add search to older Kubuntu
# installs. Module 09 copies bundled files only: no packages, downloads or builds.
set -u

if [ "${NOCTRAOS_FLAVOUR:-zorin}" != kubuntu ]; then
  echo "NOT APPLIED on the ${NOCTRAOS_FLAVOUR:-zorin} flavour: Plasma search is for Kubuntu"
  exit 0
fi

# Never execute a caller's snapshot or user-writable clone as root.
INSTALLER=/usr/local/share/noctraos/repo/install.sh
if [ ! -f "$INSTALLER" ]; then
  echo "WARN: Plasma search installer is missing; retry at the next update" >&2
  exit 1
fi
if [ -z "${NOCTRAOS_USER:-}" ] || [ "$NOCTRAOS_USER" = root ]; then
  echo "WARN: No desktop user for Plasma search setup; retry at the next update" >&2
  exit 1
fi

# The module is additive and idempotent; its shortcut helper keeps the account's
# marker. Other accounts catch up through the user migration and KDE autostart.
SUDO_USER="$NOCTRAOS_USER" bash "$INSTALLER" --only 09_super_search.sh \
  || echo "WARN: Plasma search setup did not complete; checking installed files" >&2

# A missing session or PyGObject must not block the update: the shortcut autostart
# retries without a marker. Incomplete file installation cannot recover that way,
# so do not let the updater record this migration as done until the files exist.
for file in \
  /usr/local/bin/noctraos-search \
  /usr/local/bin/noctraos-search-plasma \
  /usr/local/share/noctraos-search/browsers.py \
  /usr/local/share/noctraos-search/core.py \
  /usr/local/share/noctraos-search/krunner.py \
  /usr/local/share/noctraos-search/main.py \
  /usr/local/share/noctraos-search/preferences.py \
  /usr/share/krunner/dbusplugins/noctraos-search.desktop \
  /usr/share/dbus-1/services/org.kde.noctraos.search.service \
  /usr/share/glib-2.0/schemas/org.gnome.shell.extensions.noctraos-search.gschema.xml \
  /usr/share/glib-2.0/schemas/gschemas.compiled \
  /usr/local/share/noctraos/plasma/apply-search.sh \
  /etc/xdg/autostart/noctraos-plasma-search.desktop \
  /etc/systemd/user/noctraos-search-index.service \
  /etc/systemd/user/noctraos-search-index.timer; do
  if [ ! -f "$file" ]; then
    echo "WARN: Plasma search file is missing: $file; retry at the next update" >&2
    exit 1
  fi
done
for program in /usr/local/bin/noctraos-search /usr/local/bin/noctraos-search-plasma \
  /usr/local/share/noctraos/plasma/apply-search.sh; do
  if [ ! -x "$program" ]; then
    echo "WARN: Plasma search program is not executable: $program; retry at the next update" >&2
    exit 1
  fi
done
exit 0
