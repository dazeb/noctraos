#!/usr/bin/env bash
# Module 01: system base — apt packages, Flathub, Nerd Fonts.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

log "Updating apt package index..."
sudo apt-get update -y

CORE_PKGS=(
  build-essential curl wget git jq unzip zip fontconfig
  flatpak libglib2.0-bin dconf-cli zenity xdg-utils
  ca-certificates gnupg xterm openssh-server
)
# mise builds Python from source; these are its documented build dependencies.
PYTHON_BUILD_PKGS=(
  libssl-dev zlib1g-dev libbz2-dev libreadline-dev
  libsqlite3-dev libffi-dev liblzma-dev
)
log "Installing core packages: ${CORE_PKGS[*]} ${PYTHON_BUILD_PKGS[*]}"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${CORE_PKGS[@]}" "${PYTHON_BUILD_PKGS[@]}"

# FUSE: most AppImages mount themselves through libfuse2 (named libfuse2t64 on
# Ubuntu 24.04+, libfuse2 before the t64 transition); fuse3 provides fusermount3.
for p in fuse3 libfuse2t64 libfuse2; do
  if dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; then
    log "OK: $p already installed"
  elif apt-cache show "$p" >/dev/null 2>&1 && ! { [ "$p" = libfuse2 ] && dpkg-query -W libfuse2t64 >/dev/null 2>&1; }; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$p" \
      || warn "FUSE package failed to install: $p"
  fi
done

# Optional packages whose names vary across Zorin/Ubuntu releases.
for p in nautilus gnome-terminal nautilus-extension-gnome-terminal; do
  if apt-cache show "$p" >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$p" \
      || warn "Optional package failed to install: $p"
  else
    warn "Optional package not available in this release (skipped): $p"
  fi
done

if sudo flatpak remotes 2>/dev/null | grep -qw flathub; then
  log "OK: Flathub remote already registered"
else
  log "Registering Flathub remote..."
  sudo flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

FONT_DIR="/usr/local/share/fonts/JetBrainsMono"
# NB: no `grep -q` here — under pipefail it SIGPIPEs fc-list and the guard
# misreads "installed" as "missing", re-downloading on every run.
if fc-list 2>/dev/null | grep -i "JetBrainsMono Nerd Font" >/dev/null 2>&1; then
  log "OK: JetBrainsMono Nerd Font already installed"
else
  log "Downloading JetBrainsMono Nerd Font..."
  tmp_dir="$(mktemp -d)"
  curl -fsSL -o "$tmp_dir/JetBrainsMono.tar.xz" \
    "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz"
  sudo mkdir -p "$FONT_DIR"
  sudo tar -xJf "$tmp_dir/JetBrainsMono.tar.xz" -C "$FONT_DIR"
  sudo fc-cache -f "$FONT_DIR" >/dev/null
  rm -rf "$tmp_dir"
  log "Installed JetBrainsMono Nerd Font to $FONT_DIR"
fi

log "System base complete."
