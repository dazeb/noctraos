#!/usr/bin/env bash
# desktops: plasma
# Plasma counterpart of the module that seeds new accounts' right-click actions (the file keeps the name install/07_persistence.sh
# calls through run_desktop_module; here it seeds the Dolphin actions). Runs on every update, which re-runs module 07.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_plasma; then
  warn "NOT APPLIED on this desktop: Dolphin right-click actions for new accounts"
  exit 0
fi

sudo install -m 755 "$REPO_ROOT/bin/noctraos-fileaction" /usr/local/bin/noctraos-fileaction
ACTIONS=/etc/skel/.local/share/noctraos/file-actions
MENUS=/etc/skel/.local/share/kio/servicemenus
sudo mkdir -p "$ACTIONS" "$MENUS"
for src in "$REPO_ROOT/configs/nautilus-scripts/"*; do
  [ -f "$src" ] || continue
  sudo install -m 755 "$src" "$ACTIONS/$(basename "$src")"
done
sudo install -m 755 "$REPO_ROOT/configs/plasma/servicemenus/noctraos-actions.desktop" "$MENUS/noctraos-actions.desktop"
sudo chmod -R go+rX /etc/skel/.local/share/noctraos /etc/skel/.local/share/kio
