#!/usr/bin/env bash
# Module 04b: Omarchy-style workstation applications with Ubuntu equivalents.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

# Policy: Flatpak (and AppImage) first. apt is for CLI tools, system tools and things
# that need deep host integration. GUI apps live in FLATPAK_APPS below; module 04c
# retires the apt copy of each once its Flatpak is installed.
# Keep this list to packages from the Ubuntu/Zorin archive. Check each package
# before installing so a renamed package cannot break the rest of the setup.
APT_APPS=(
  avahi-daemon bat btop brightnessctl clang cups cups-filters
  cups-pk-helper ddcutil docker.io docker-compose-v2 eza
  exfatprogs fd-find ffmpeg ffmpegthumbnailer fzf gh
  gnome-disk-utility gnome-sushi gnome-tweaks gvfs-backends
  imagemagick inotify-tools inxi libsecret-tools
  man-db ncdu plocate qrencode ripgrep ruby
  socat system-config-printer tesseract-ocr tldr tmux whois
  wl-clipboard yt-dlp zoxide
)
missing=()
for package in "${APT_APPS[@]}"; do
  # "apt-cache show" succeeds for packages with no installable candidate (e.g. tldr on 26.04,
  # where tealdeer is the replacement), and one such name aborts the whole apt-get install.
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
  org.libreoffice.LibreOffice
  org.videolan.VLC
  io.mpv.Mpv
  com.obsproject.Studio
  org.kde.kdenlive
  org.gnome.gThumb
  org.gnome.Evince
  org.flameshot.Flameshot
  com.github.xournalpp.xournalpp
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
