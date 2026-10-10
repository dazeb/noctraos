#!/usr/bin/env bash
# desktops: gnome
# Module 05: mouse ergonomics — Nautilus right-click script actions.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_gnome; then
  warn "NOT APPLIED on this desktop: Nautilus right-click scripts (GNOME Files)"
  exit 0
fi

SCRIPTS_DIR="$TARGET_HOME/.local/share/nautilus/scripts"
as_user mkdir -p "$SCRIPTS_DIR"
# Retire old installer-owned menu actions; keep the user's editor settings. The underscore
# names are the previous spelling: a menu label treats "_" as a mnemonic marker and drops it
# ("AskAItoExplain"), so the scripts are named with plain spaces now.
for old in Open_in_VSCodium Ask_AI_to_Explain Open_Terminal_Here Open_in_VS_Code; do
  as_user rm -f "$SCRIPTS_DIR/$old"
done

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
