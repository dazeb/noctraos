#!/usr/bin/env bash
# desktops: plasma
# Plasma desktop module 04: the KDE counterparts of the GNOME system tools (disk utility, previews, viewers).
# Decision 5 of the Kubuntu plan: KDE apps on the kubuntu flavour. Runs right after install/04_workstation_apps.sh.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_plasma; then
  warn "NOT APPLIED on this desktop: KDE Partition Manager, Okular, Gwenview and Ark"
  exit 0
fi

APT_APPS=(partitionmanager okular gwenview ark)
missing=()
for package in "${APT_APPS[@]}"; do
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
  log "Installing KDE apps: ${missing[*]}"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-confold "${missing[@]}" \
    || warn "Some KDE apps failed to install: ${missing[*]}"
fi
