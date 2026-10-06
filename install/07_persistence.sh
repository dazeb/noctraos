#!/usr/bin/env bash
# Module 07: persistence — /etc/skel defaults for new users + noc management CLI.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

log "Syncing defaults into /etc/skel (applies to every user created from now on)..."
sudo mkdir -p \
  /etc/skel/.config/mise \
  /etc/skel/.config/copyq \
  /etc/skel/.config/herdr \
  /etc/skel/.config/btop/themes \
  /etc/skel/.config/autostart \
  /etc/skel/.config/Code/User \
  /etc/skel/.continue \
  /etc/skel/.local/share/nautilus/scripts

sudo install -m 644 "$REPO_ROOT/configs/mise/config.toml" \
  /etc/skel/.config/mise/config.toml
sudo install -m 644 "$REPO_ROOT/configs/vscode/continue_config.yaml" \
  /etc/skel/.continue/config.yaml
sudo install -m 644 "$REPO_ROOT/configs/vscode/settings.json" \
  /etc/skel/.config/Code/User/settings.json
for old in Open_in_VSCodium Ask_AI_to_Explain Open_Terminal_Here Open_in_VS_Code; do
  sudo rm -f "/etc/skel/.local/share/nautilus/scripts/$old"
done
sudo install -m 644 "$REPO_ROOT/configs/copyq/copyq.conf" \
  /etc/skel/.config/copyq/copyq.conf
sudo install -m 644 "$REPO_ROOT/configs/theme/herdr.toml" \
  /etc/skel/.config/herdr/config.toml
sudo install -m 644 "$REPO_ROOT/configs/theme/noctraos-btop.theme" \
  /etc/skel/.config/btop/themes/noctraos.theme
if [ ! -f /etc/skel/.config/btop/btop.conf ]; then
  printf 'color_theme = "noctraos"\n' | sudo tee /etc/skel/.config/btop/btop.conf >/dev/null
fi
sudo install -m 644 "$REPO_ROOT/configs/autostart/copyq.desktop" \
  /etc/skel/.config/autostart/copyq.desktop
sudo python3 "$REPO_ROOT/scripts/seed-password-store.py" /etc/skel >/dev/null \
  || warn "Could not seed the keyring-free password store for new users"
for src in "$REPO_ROOT/configs/nautilus-scripts/"*; do
  [ -f "$src" ] || continue
  sudo install -m 755 "$src" "/etc/skel/.local/share/nautilus/scripts/$(basename "$src")"
done
sudo chmod -R go+rX /etc/skel/.config /etc/skel/.continue /etc/skel/.local
# ...except the keyring directory, which stays private to the account.
[ -d /etc/skel/.local/share/keyrings ] && sudo chmod -R go-rwx /etc/skel/.local/share/keyrings

log "Installing noc management CLI..."
# Clean break from the pre-rename CLI name (zom → noc).
sudo rm -f /usr/local/bin/zom /usr/local/bin/zom-menu /usr/local/bin/zom-gpu \
  /usr/local/share/applications/zom-menu.desktop
sudo install -m 755 "$REPO_ROOT/bin/noc" /usr/local/bin/noc
sudo install -m 755 "$REPO_ROOT/bin/noc-gpu" /usr/local/bin/noc-gpu

log "Installing the Control Panel (replaces the old zenity noc-menu)..."
# Clean break: the zenity panel and its launcher are gone, not aliased.
sudo rm -f /usr/local/bin/noc-menu /usr/local/share/applications/noc-menu.desktop
sudo mkdir -p /usr/local/share/noctraos-control
for f in "$REPO_ROOT"/control/*.py; do
  sudo install -m 644 "$f" "/usr/local/share/noctraos-control/$(basename "$f")"
done
sudo install -m 755 "$REPO_ROOT/bin/noctraos-control" /usr/local/bin/noctraos-control
# The launcher (configs/applications/noctraos-control.desktop) and icon are installed by module 06.

log "Persistence complete: new users inherit mise, Continue and Nautilus script defaults."
log "Manage the workstation with: noc (CLI) or the NoctraOS Control Panel (GUI)."
