#!/usr/bin/env bash
# Module 04c: application policy.
#   - Flatpak (Flathub) and AppImage first. apt stays for CLI tools, system tools and
#     things that need deep host integration (VS Code, CopyQ, Docker).
#   - Retire the apt copy of an app once its Flatpak replacement is installed.
#   - Retire apps we do not want on the image, and hide launchers that only confuse.
# Everything here is reversible: removals are plain `apt-get remove` (user data stays,
# no purge/autoremove), hiding is an override file in /usr/local/share/applications.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

pkg_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null
}
flatpak_has() { sudo flatpak info "$1" >/dev/null 2>&1; }

# Installed package names matching a dpkg glob, e.g. installed_matching 'libreoffice*'.
installed_matching() {
  dpkg-query -W -f='${binary:Package} ${Status}\n' "$1" 2>/dev/null \
    | awk '$NF == "installed" { sub(/:.*/, "", $1); print $1 }'
}

# ---- AppImage support -------------------------------------------------------------
# AppImages need FUSE 2 (libfuse2t64 on Ubuntu 24.04) to run. Module 04d installs
# AppManager for drag-and-drop installs; a downloaded AppImage also runs once it is
# marked executable.
if pkg_installed libfuse2t64; then
  log "OK: libfuse2t64 already installed (AppImage support)"
elif apt-cache show libfuse2t64 >/dev/null 2>&1; then
  log "Installing libfuse2t64 (AppImage support)..."
  apt_install libfuse2t64 || warn "libfuse2t64 install failed — AppImages will not run"
else
  warn "libfuse2t64 not available in this release — AppImages may not run"
fi

# ---- safe apt removal -------------------------------------------------------------
# If apt would also remove any of these, the desktop would go with the app: skip instead.
# (gnome-shell itself, not its extensions: the Zorin Connect extension may go, but the
# menu/taskbar/desktop-icons extensions our Start button and dock hook are protected.)
PROTECTED_RE='^(zorin-os|ubuntu-desktop|ubuntu-standard|ubuntu-minimal|gdm3|nautilus|gnome-control-center|network-manager|systemd|xorg|xserver|plymouth|grub|sudo|apt|dpkg|libc6|flatpak|ollama|gnome-shell(-common)?$|gnome-shell-extension-zorin-(menu|taskbar|desktop-icons))'

retire_apt() { # retire_apt <why> <package>...
  local why="$1" requested=() present=() ok=() p plan plan_out collateral hit
  shift
  requested=("$@")
  for p in "${requested[@]}"; do pkg_installed "$p" && present+=("$p"); done
  [ "${#present[@]}" -gt 0 ] || return 0
  # Judge each package on its own, so one that cannot go does not hold up the rest, and only
  # by what apt would remove BEYOND what we asked for: a package we named may itself be called
  # zorin-os-something and still be fine to remove. Simulate first: "Remv <pkg> ..." lines are
  # exactly what apt would remove.
  for p in "${present[@]}"; do
    # apt cannot always plan a removal (e.g. libreoffice-style-colibre: removing it would break
    # libreoffice-core). Under pipefail that failure would abort the whole install, so a
    # package whose removal cannot be simulated is kept, like one that would drag the desktop.
    if ! plan_out="$(sudo apt-get -s remove "$p" 2>/dev/null)"; then
      warn "Keeping $p ($why): apt cannot plan its removal"
      continue
    fi
    plan="$(awk '/^Remv /{print $2}' <<<"$plan_out")"
    collateral="$(printf '%s\n' $plan | grep -vxF -f <(printf '%s\n' "${requested[@]}") || true)"
    hit="$(grep -E "$PROTECTED_RE" <<<"$collateral" || true)"
    if [ -n "$hit" ]; then
      warn "Keeping $p ($why): removing it would also remove: $(tr '\n' ' ' <<<"$hit")"
    else
      ok+=("$p")
    fi
  done
  [ "${#ok[@]}" -gt 0 ] || return 0
  log "Removing $why: ${ok[*]}"
  sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y "${ok[@]}" \
    || warn "Could not remove: ${ok[*]}"
}

replace_with_flatpak() { # replace_with_flatpak <flatpak id> <package>...
  local id="$1"
  shift
  if [ "$#" -eq 0 ]; then return 0; fi
  if flatpak_has "$id"; then
    retire_apt "the apt copy (replaced by Flatpak $id)" "$@"
  else
    warn "Keeping apt $* — Flatpak $id is not installed"
  fi
}

# ---- the apt copy goes once the Flatpak is there ------------------------------------
mapfile -t LIBREOFFICE_PKGS < <(installed_matching 'libreoffice*')
replace_with_flatpak org.libreoffice.LibreOffice "${LIBREOFFICE_PKGS[@]}"
mapfile -t VLC_PKGS < <(installed_matching 'vlc*')
replace_with_flatpak org.videolan.VLC "${VLC_PKGS[@]}"
replace_with_flatpak io.mpv.Mpv mpv
replace_with_flatpak com.obsproject.Studio obs-studio
replace_with_flatpak org.kde.kdenlive kdenlive
replace_with_flatpak org.gnome.gThumb gthumb
replace_with_flatpak org.gnome.Evince evince
replace_with_flatpak org.flameshot.Flameshot flameshot
replace_with_flatpak com.github.xournalpp.xournalpp xournalpp

# ---- apps we do not want ------------------------------------------------------------
# Chromium (Flatpak) is the browser; Brave from the base image would be a second one that
# also prompts for the keyring. Videos and Rhythmbox are covered by VLC, Brasero is a
# disc burner, Tour clashes with our own first-run onboarding, Weather has our own widget.
# Zorin's own extras are not part of what NoctraOS is: Appearance only switches Zorin's
# layouts and themes (our branding fixes both; wallpapers are Settings > Background or
# `noc bg`), Connect is the phone integration, Web Apps and Windows App Support are
# Zorin's. Removing Appearance also takes its two "layouts" packages; the menu, taskbar
# and desktop-icons extensions are separate packages and stay (apt confirms this in the
# simulation, and the guard refuses otherwise). Neovim is not shipped.
retire_apt "apps we do not ship" \
  brave-browser brasero rhythmbox totem gnome-tour gnome-weather malcontent-gui evolution \
  zorin-appearance zorin-connect webapp-manager \
  zorin-windows-app-support-installation-shortcut neovim neovim-runtime \
  zorin-gnome-tour-autostart zorin-os-tour-video

# Zorin's first-login "Welcome to Zorin OS" tour (GNOME Tour) is started from a per-user
# autostart file copied out of /etc/skel. NoctraOS has its own welcome (noctraos-welcome).
# The package removal above drops the skel copy; remove any that already reached an account.
for f in /etc/skel/.config/autostart/zorin-gnome-tour-autostart.desktop \
         "$TARGET_HOME/.config/autostart/zorin-gnome-tour-autostart.desktop"; do
  [ -f "$f" ] && sudo rm -f "$f"
done

# Vim is the exception: vim-common/vim-tiny are depended on by Zorin's zorin-os-minimal
# metapackage, so removing them would remove that too (the guard would refuse). It is not
# in the list; its launcher is hidden below instead.

# Gear Lever (AppImage manager) is no longer shipped (AppManager, module 04d, replaces it); remove it where an earlier run put it.
if flatpak_has it.mijorus.gearlever; then
  log "Removing Flatpak it.mijorus.gearlever (not shipped)"
  sudo flatpak uninstall -y --noninteractive it.mijorus.gearlever \
    || warn "Could not remove Gear Lever"
fi

# ---- launchers that only confuse ------------------------------------------------------
# Packaged launchers stay as they are; a same-named file in /usr/local/share/applications
# (earlier in the XDG data dirs) overrides it with NoDisplay=true. Delete it to undo.
HIDE_LAUNCHERS=(
  texdoctk.desktop info.desktop display-im6.q16.desktop vim.desktop
  debian-xterm.desktop debian-uxterm.desktop
  alacarte.desktop                                  # Main Menu: cannot edit our menu tree
  org.gnome.SystemMonitor.desktop gnome-system-monitor-kde.desktop  # Mission Center replaces it
  com.zorin.desktop.upgrader.desktop                # "Upgrade Zorin OS": not our upgrade path
  org.freedesktop.IBus.Setup.desktop im-config.desktop org.gnome.PowerStats.desktop
  # Fallbacks if a removal above was refused: never leave these in the menu.
  zorin-appearance.desktop zorin-connect.desktop install-zorin-windows-app-support.desktop
)
hide_launcher() {
  local id="$1" src="/usr/share/applications/$1" dst="/usr/local/share/applications/$1"
  [ -f "$src" ] || return 0
  if [ -f "$dst" ] && grep '^NoDisplay=true' "$dst" >/dev/null; then
    return 0
  fi
  sudo mkdir -p /usr/local/share/applications
  # NoDisplay must sit in the [Desktop Entry] group, not after the last [Desktop Action].
  awk '/^NoDisplay=/ {next} {print} /^\[Desktop Entry\]/ {print "NoDisplay=true"}' "$src" \
    | sudo tee "$dst" >/dev/null
  log "Hidden launcher: $id"
}
for id in "${HIDE_LAUNCHERS[@]}"; do
  hide_launcher "$id"
done

sudo update-desktop-database >/dev/null 2>&1 || true
log "Application policy complete."
