#!/usr/bin/env bash
# Module 04b: Omarchy-style workstation applications with Ubuntu equivalents.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

# Keep this list to packages from the Ubuntu/Zorin archive. Check each package
# before installing so a renamed package cannot break the rest of the setup.
APT_APPS=(
  avahi-daemon bat btop brightnessctl clang cups cups-filters
  cups-pk-helper ddcutil docker.io docker-compose-v2 eza evince
  exfatprogs fd-find ffmpeg ffmpegthumbnailer flameshot fzf gh
  gnome-disk-utility gnome-sushi gnome-tweaks gthumb gvfs-backends
  imagemagick inotify-tools inxi kdenlive libsecret-tools libreoffice
  man-db mpv ncdu neovim obs-studio plocate qrencode ripgrep ruby
  socat system-config-printer tesseract-ocr tldr tmux whois
  wl-clipboard xournalpp yt-dlp zoxide
)
missing=()
for package in "${APT_APPS[@]}"; do
  if ! apt-cache show "$package" >/dev/null 2>&1; then
    warn "Ubuntu package unavailable: $package"
  elif dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; then
    log "OK: $package already installed"
  else
    missing+=("$package")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  log "Installing workstation packages: ${missing[*]}"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
fi

# These app IDs are published on Flathub for both x86_64 and aarch64.
FLATPAK_APPS=(
  org.chromium.Chromium
  md.obsidian.Obsidian
  org.localsend.localsend_app
  com.github.PintaProject.Pinta
  com.moonlight_stream.Moonlight
)
for app in "${FLATPAK_APPS[@]}"; do
  if sudo flatpak info "$app" >/dev/null 2>&1; then
    log "OK: $app already installed"
  else
    log "Installing Flatpak: $app"
    sudo flatpak install -y --noninteractive flathub "$app" \
      || warn "Flatpak install failed: $app"
  fi
done

sudo update-desktop-database >/dev/null 2>&1 || true
log "Workstation application set complete."
