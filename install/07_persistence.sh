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
if [ -f /etc/skel/.local/share/nautilus/scripts/Open_in_VSCodium ]; then
  sudo rm -f /etc/skel/.local/share/nautilus/scripts/Open_in_VSCodium
fi
sudo install -m 644 "$REPO_ROOT/configs/copyq/copyq.conf" \
  /etc/skel/.config/copyq/copyq.conf
sudo install -m 644 "$REPO_ROOT/configs/theme/herdr.toml" \
  /etc/skel/.config/herdr/config.toml
sudo install -m 644 "$REPO_ROOT/configs/theme/zorin-ai-btop.theme" \
  /etc/skel/.config/btop/themes/zorin-ai.theme
if [ ! -f /etc/skel/.config/btop/btop.conf ]; then
  printf 'color_theme = "zorin-ai"\n' | sudo tee /etc/skel/.config/btop/btop.conf >/dev/null
fi
sudo install -m 644 "$REPO_ROOT/configs/autostart/copyq.desktop" \
  /etc/skel/.config/autostart/copyq.desktop
for src in "$REPO_ROOT/configs/nautilus-scripts/"*; do
  [ -f "$src" ] || continue
  sudo install -m 755 "$src" "/etc/skel/.local/share/nautilus/scripts/$(basename "$src")"
done
sudo chmod -R go+rX /etc/skel/.config /etc/skel/.continue /etc/skel/.local

log "Installing noc management CLI..."
# Clean break from the pre-rename CLI name (zom → noc).
sudo rm -f /usr/local/bin/zom /usr/local/bin/zom-menu /usr/local/bin/zom-gpu \
  /usr/local/share/applications/zom-menu.desktop
sudo install -m 755 "$REPO_ROOT/bin/noc" /usr/local/bin/noc
sudo install -m 755 "$REPO_ROOT/bin/noc-menu" /usr/local/bin/noc-menu
sudo install -m 755 "$REPO_ROOT/bin/noc-gpu" /usr/local/bin/noc-gpu

sudo mkdir -p /usr/local/share/applications
sudo tee /usr/local/share/applications/noc-menu.desktop >/dev/null <<'EOF'
[Desktop Entry]
Type=Application
Name=zorin-ai Control Panel
Comment=Update and health-check your zorin-ai workstation
Exec=noc-menu
Icon=applications-system
Terminal=false
Categories=System;
EOF

log "Persistence complete: new users inherit mise, Continue and Nautilus script defaults."
log "Manage the workstation with: noc (CLI) or noc-menu (GUI)."
