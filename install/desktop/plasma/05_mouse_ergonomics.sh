#!/usr/bin/env bash
# desktops: plasma
# Plasma module 05: mouse ergonomics — the Dolphin right-click actions (Open in VS Code, Ask AI to Explain, Open Terminal Here).
# Dolphin service menus call noctraos-fileaction, which runs the same scripts the Nautilus menu uses.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_plasma; then
  warn "NOT APPLIED on this desktop: Dolphin right-click actions"
  exit 0
fi

sudo install -m 755 "$REPO_ROOT/bin/noctraos-fileaction" /usr/local/bin/noctraos-fileaction
ACTIONS="$TARGET_HOME/.local/share/noctraos/file-actions"
MENUS="$TARGET_HOME/.local/share/kio/servicemenus"
as_user mkdir -p "$ACTIONS" "$MENUS"
for src in "$REPO_ROOT/configs/nautilus-scripts/"*; do
  [ -f "$src" ] || continue
  as_user install -m 755 "$src" "$ACTIONS/$(basename "$src")"
done
# Dolphin only runs a user-installed service menu that is executable.
as_user install -m 755 "$REPO_ROOT/configs/plasma/servicemenus/noctraos-actions.desktop" "$MENUS/noctraos-actions.desktop"
log "OK: right-click a file in Dolphin → NoctraOS → 'Open in VS Code' / 'Ask AI to Explain' / 'Open Terminal Here'"
log "Mouse ergonomics complete."
