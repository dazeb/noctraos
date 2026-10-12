#!/usr/bin/env bash
# desktops: plasma
# Plasma desktop module 01: the KDE file manager and terminal, plus the two dialog tools the right-click actions use.
# They come with Kubuntu, so this is a no-op there; it keeps a Plasma desktop that lacks them complete.
# Runs right after module 01 (install.sh), also with --skip-gui.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_plasma; then
  warn "NOT APPLIED on this desktop: Dolphin and Konsole packages"
  exit 0
fi

missing=()
for p in dolphin konsole kdialog zenity libnotify-bin; do
  if dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; then
    continue
  elif apt-cache show "$p" >/dev/null 2>&1; then
    missing+=("$p")
  else
    warn "Optional package not available in this release (skipped): $p"
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  log "Installing: ${missing[*]}"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-confold "${missing[@]}" \
    || warn "Some Plasma base packages failed to install: ${missing[*]}"
fi
