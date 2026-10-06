#!/usr/bin/env bash
# Module 09: Super+Space system search and the Noctra start button.
# Two GNOME Shell extensions plus the user-owned search index. Per-account
# enablement happens at first login via /etc/xdg/autostart (and now, for the
# installing user); later user choices are never overwritten.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

SEARCH_UUID="noctraos-search@noctraos.local"
BRANDING_UUID="noctraos-branding@noctraos.local"
START_UUID="noctraos-start@noctraos.local"
EXT_DIR="/usr/share/gnome-shell/extensions"

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

log "Installing Super+Space search and the Noctra start button..."

# The settings window and launcher use the system Python's PyGObject.
for pkg in python3-gi gir1.2-gtk-3.0; do
  if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; then
    apt_install "$pkg"
  fi
done

for uuid in "$SEARCH_UUID" "$BRANDING_UUID" "$START_UUID"; do
  for f in "$REPO_ROOT/extensions/$uuid"/*; do
    install_if_changed 644 "$f" "$EXT_DIR/$uuid/$(basename "$f")"
  done
done

for f in "$REPO_ROOT"/search/*.py; do
  install_if_changed 644 "$f" "/usr/local/share/noctraos-search/$(basename "$f")"
done
install_if_changed 755 "$REPO_ROOT/bin/noctraos-search" /usr/local/bin/noctraos-search
install_if_changed 755 "$REPO_ROOT/bin/noctraos-weather" /usr/local/bin/noctraos-weather
install_if_changed 644 "$REPO_ROOT/help/index.html" /usr/local/share/noctraos/help/index.html
install_if_changed 755 "$REPO_ROOT/branding/setup-branding.py" /usr/local/share/noctraos/setup-branding.py

for SCHEMA_FILE in org.gnome.shell.extensions.noctraos-search.gschema.xml \
                   org.gnome.shell.extensions.noctraos-start.gschema.xml; do
  install_if_changed 644 "$REPO_ROOT/configs/gsettings/$SCHEMA_FILE" "/usr/share/glib-2.0/schemas/$SCHEMA_FILE"
done
# System-wide defaults (override files are compiled together with the schemas).
install_if_changed 644 "$REPO_ROOT/configs/gsettings/90_noctraos-updates.gschema.override" \
  /usr/share/glib-2.0/schemas/90_noctraos-updates.gschema.override
if [ "$CHANGED" -eq 1 ] || [ ! -f /usr/share/glib-2.0/schemas/gschemas.compiled ]; then
  sudo glib-compile-schemas /usr/share/glib-2.0/schemas
fi

# Periodic file index: a systemd *user* unit enabled for every account.
for unit in noctraos-search-index.service noctraos-search-index.timer; do
  install_if_changed 644 "$REPO_ROOT/configs/systemd/$unit" "/etc/systemd/user/$unit"
done
if [ ! -L /etc/systemd/user/timers.target.wants/noctraos-search-index.timer ]; then
  sudo systemctl --global enable noctraos-search-index.timer >/dev/null 2>&1 \
    || warn "Could not enable the search index timer"
fi

for f in noctraos-search-setup.desktop noctraos-branding.desktop noctraos-welcome.desktop; do
  install_if_changed 644 "$REPO_ROOT/configs/autostart/$f" "/etc/xdg/autostart/$f"
done

# Icon + settings launcher are installed by module 06's icon/desktop globs.
# Enable for the installing user now; both setups are once-per-account.
as_user /usr/local/bin/noctraos-search --setup \
  || warn "Super+Space setup failed — it will retry at next login"
as_user /usr/bin/python3 /usr/local/share/noctraos/setup-branding.py \
  || warn "Start-button setup failed — it will retry at next login"

log "OK: Super+Space search installed — takes effect after sign out/in"
