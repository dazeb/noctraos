#!/usr/bin/env bash
# desktops: plasma
# Plasma module 09: Super+Space system search. On GNOME this is a Shell extension; on KDE Plasma the
# shortcut opens KRunner, and a KRunner DBus runner (search/krunner.py) answers with the same results.
# The index, the settings and the search code are shared with the GNOME flavour, so this module installs
# the same search app and settings, then adds the KRunner bridge and the per-account shortcut setup.
# Runs from install.sh after 08_shell_theme.sh; also with --skip-gui (module order keeps it last).
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_plasma; then
  warn "NOT APPLIED on this desktop: Super+Space search (KRunner runner, shortcut and search index)"
  exit 0
fi

# install_if_changed MODE SRC DST — copy only when content differs (idempotent).
install_if_changed() {
  local mode="$1" src="$2" dst="$3"
  if cmp -s "$src" "$dst" 2>/dev/null; then
    return 0
  fi
  sudo install -D -m "$mode" "$src" "$dst"
  CHANGED=1
}
CHANGED=0

log "Installing Super+Space search (KRunner runner)..."

# The shared search app: the index, the clipboard bridge, the browser history and the settings window.
for f in "$REPO_ROOT"/search/*.py; do
  install_if_changed 644 "$f" "/usr/local/share/noctraos-search/$(basename "$f")"
done
install_if_changed 755 "$REPO_ROOT/bin/noctraos-search" /usr/local/bin/noctraos-search
install_if_changed 755 "$REPO_ROOT/bin/noctraos-search-plasma" /usr/local/bin/noctraos-search-plasma
install_if_changed 755 "$REPO_ROOT/bin/noctraos-weather" /usr/local/bin/noctraos-weather

# The settings schema both flavours share (web provider, which sources to search, index roots).
install_if_changed 644 "$REPO_ROOT/configs/gsettings/org.gnome.shell.extensions.noctraos-search.gschema.xml" \
  /usr/share/glib-2.0/schemas/org.gnome.shell.extensions.noctraos-search.gschema.xml
if [ "$CHANGED" -eq 1 ] || [ ! -f /usr/share/glib-2.0/schemas/gschemas.compiled ]; then
  sudo glib-compile-schemas /usr/share/glib-2.0/schemas
fi

# Periodic file index: a systemd *user* unit enabled for every account (the same one GNOME uses).
for unit in noctraos-search-index.service noctraos-search-index.timer; do
  install_if_changed 644 "$REPO_ROOT/configs/systemd/$unit" "/etc/systemd/user/$unit"
done
if [ ! -L /etc/systemd/user/timers.target.wants/noctraos-search-index.timer ]; then
  sudo systemctl --global enable noctraos-search-index.timer >/dev/null 2>&1 \
    || warn "Could not enable the search index timer"
fi

# The KRunner side: the runner metadata KRunner scans, and the D-Bus activation file that starts the
# runner on demand (nothing runs until the first search).
install_if_changed 644 "$REPO_ROOT/configs/plasma/krunner/noctraos-search.desktop" \
  /usr/share/krunner/dbusplugins/noctraos-search.desktop
install_if_changed 644 "$REPO_ROOT/configs/plasma/krunner/org.kde.noctraos.search.service" \
  /usr/share/dbus-1/services/org.kde.noctraos.search.service
install_if_changed 644 "$REPO_ROOT/configs/plasma/krunner/noctraos-search-settings.desktop" \
  /usr/local/share/applications/noctraos-search-settings.desktop

# Super+Space: once per account, from the session (KGlobalAccel takes live changes; the module's own run
# below covers the installing user, and the autostart entry covers every account created later).
install_if_changed 755 "$REPO_ROOT/configs/plasma/apply-search.sh" /usr/local/share/noctraos/plasma/apply-search.sh
install_if_changed 644 "$REPO_ROOT/configs/autostart/noctraos-plasma-search.desktop" \
  /etc/xdg/autostart/noctraos-plasma-search.desktop

if as_user /usr/local/share/noctraos/plasma/apply-search.sh; then
  log "Super+Space shortcut setup complete (existing choices kept)."
else
  warn "NOT APPLIED: Super+Space shortcut — set it in System Settings > Shortcuts, or run apply-search.sh again"
fi
log "KRunner search files installed — files, folders, browser history and clipboard (search settings: noctraos-search --settings)"
