#!/usr/bin/env bash
# desktops: gnome
# GNOME desktop module 07: the Nautilus right-click scripts every new account starts with (/etc/skel). Called from
# install/07_persistence.sh through run_desktop_module, so it also runs on every update (which re-runs module 07).
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_gnome; then
  warn "NOT APPLIED on this desktop: Nautilus scripts for new accounts"
  exit 0
fi

SKEL_SCRIPTS=/etc/skel/.local/share/nautilus/scripts
sudo mkdir -p "$SKEL_SCRIPTS"
for old in Open_in_VSCodium Ask_AI_to_Explain Open_Terminal_Here Open_in_VS_Code; do
  sudo rm -f "$SKEL_SCRIPTS/$old"
done
for src in "$REPO_ROOT/configs/nautilus-scripts/"*; do
  [ -f "$src" ] || continue
  sudo install -m 755 "$src" "$SKEL_SCRIPTS/$(basename "$src")"
done
sudo chmod -R go+rX /etc/skel/.local/share/nautilus
