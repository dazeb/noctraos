#!/usr/bin/env bash
# Module 05: mouse ergonomics — Nautilus right-click script actions.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

SCRIPTS_DIR="$TARGET_HOME/.local/share/nautilus/scripts"
as_user mkdir -p "$SCRIPTS_DIR"
# Retire the old installer-owned menu action; keep the user's editor settings.
if as_user test -f "$SCRIPTS_DIR/Open_in_VSCodium"; then
  as_user rm -f "$SCRIPTS_DIR/Open_in_VSCodium"
fi

for src in "$REPO_ROOT/configs/nautilus-scripts/"*; do
  [ -f "$src" ] || continue
  name="$(basename "$src")"
  as_user install -m 755 "$src" "$SCRIPTS_DIR/$name"
  log "Installed Nautilus script: $name"
done

# Make Nautilus rescan its script folder right away.
as_user nautilus -q >/dev/null 2>&1 || true

log "OK: right-click any file in Files (Nautilus) → Scripts →"
log "      'Open in VS Code' / 'Ask AI to Explain' / 'Open Terminal Here'"
log "Mouse ergonomics complete."
