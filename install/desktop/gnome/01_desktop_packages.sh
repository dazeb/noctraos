#!/usr/bin/env bash
# desktops: gnome
# GNOME desktop module 01: the GNOME file manager and terminal. They come with Zorin, so this is a no-op there; it keeps a
# GNOME desktop that lacks them complete. Runs right after module 01 (install.sh), also with --skip-gui.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_gnome; then
  warn "NOT APPLIED on this desktop: GNOME Files and GNOME Terminal packages"
  exit 0
fi

# Optional packages whose names vary across Zorin/Ubuntu releases.
for p in nautilus gnome-terminal nautilus-extension-gnome-terminal; do
  if apt-cache show "$p" >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$p" \
      || warn "Optional package failed to install: $p"
  else
    warn "Optional package not available in this release (skipped): $p"
  fi
done
