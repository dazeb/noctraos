#!/usr/bin/env bash
# desktops: gnome
# GNOME desktop module 04: the GNOME system tools of the workstation app set (disk utility, file previews, tweaks).
# Runs right after install/04_workstation_apps.sh and before the app policy (04c), as they did when they were part of it.
# The Plasma counterparts are a product decision for the kubuntu flavour (docs/flavours.md), not made here.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_gnome; then
  warn "NOT APPLIED on this desktop: GNOME Disks, Sushi and Tweaks"
  exit 0
fi

APT_APPS=(gnome-disk-utility gnome-sushi gnome-tweaks)
missing=()
for package in "${APT_APPS[@]}"; do
  # Same check as module 04_workstation_apps: a package with no installable candidate must not abort the apt-get install.
  candidate="$(apt-cache policy "$package" 2>/dev/null | awk '/^ *Candidate:/ {print $2}')"
  if [ -z "$candidate" ] || [ "$candidate" = "(none)" ]; then
    warn "Ubuntu package unavailable (no installable candidate): $package"
  elif dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; then
    log "OK: $package already installed"
  else
    missing+=("$package")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  log "Installing GNOME system tools: ${missing[*]}"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
fi
