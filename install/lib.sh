#!/usr/bin/env bash
# Shared helpers for noctraos install modules. Sourced by install.sh and each module.
: "${REPO_ROOT:?REPO_ROOT must be set — run modules via install.sh}"
: "${TARGET_USER:?TARGET_USER must be set}"
: "${TARGET_UID:?TARGET_UID must be set}"
: "${TARGET_HOME:?TARGET_HOME must be set}"

log()  { printf '\033[1;36m[noctraos]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[noctraos WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[noctraos ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

apt_install() {
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

# Run a command inside the target user's desktop session (HOME, XDG runtime dir,
# session bus) so dconf/gsettings and user-scoped writes land in the real running
# GNOME session. Never use dbus-launch here — it creates a throwaway bus.
as_user() {
  local -a envs=(
    "HOME=$TARGET_HOME"
    "USER=$TARGET_USER"
    "XDG_RUNTIME_DIR=/run/user/$TARGET_UID"
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$TARGET_UID/bus"
    "PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  )
  if [ "$(id -un)" = "$TARGET_USER" ]; then
    env "${envs[@]}" "$@"
  else
    sudo -u "$TARGET_USER" env "${envs[@]}" "$@"
  fi
}

# True if a .desktop entry is visible to the target user
# (system, local, or flatpak export directories).
desktop_file_exists() {
  local f="$1" d
  for d in \
    "/usr/share/applications" \
    "/usr/local/share/applications" \
    "$TARGET_HOME/.local/share/applications" \
    "/var/lib/flatpak/exports/share/applications" \
    "$TARGET_HOME/.local/share/flatpak/exports/share/applications"; do
    [ -f "$d/$f" ] && return 0
  done
  return 1
}

# Install the NoctraOS launchers (configs/applications/*.desktop) and icons (assets/icons/noctraos-*.svg) system-wide, only
# when a file is missing or differs, so a second run changes nothing. Used by module 06 (fresh installs) and module 07, which
# an update re-runs: a changed launcher reaches machines that already have it without a migration. Touches no setting.
install_launchers() {
  local repo="$1" f dest changed=0
  sudo mkdir -p /usr/local/share/applications /usr/local/share/icons/hicolor/scalable/apps
  for f in "$repo"/configs/applications/*.desktop; do
    [ -f "$f" ] || continue
    dest="/usr/local/share/applications/$(basename "$f")"
    cmp -s "$f" "$dest" 2>/dev/null || { sudo install -m 644 "$f" "$dest" && changed=1; }
  done
  for f in "$repo"/assets/icons/noctraos-*.svg; do
    [ -f "$f" ] || continue
    dest="/usr/local/share/icons/hicolor/scalable/apps/$(basename "$f")"
    cmp -s "$f" "$dest" 2>/dev/null || { sudo install -m 644 "$f" "$dest" && changed=1; }
  done
  if [ "$changed" = 1 ]; then
    sudo update-desktop-database >/dev/null 2>&1 || true
    sudo gtk-update-icon-cache -q -t -f /usr/local/share/icons/hicolor 2>/dev/null || true
  fi
  return 0
}

# desktop_name — the session desktop for messages ("KDE", "GNOME", "unknown").
desktop_name() { printf '%s' "${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-unknown}}"; }

# desktop_is_gnome — success only when GNOME Shell is available as the desktop:
# the gnome-shell binary must exist AND (XDG_CURRENT_DESKTOP names GNOME, or the
# binary is present). GNOME-only modules (06, 08, 09) use it to skip honestly
# instead of reporting success on KDE Plasma, where nothing they write is read.
desktop_is_gnome() {
  have gnome-shell || return 1
  case "${XDG_CURRENT_DESKTOP:-}" in
    "") return 0 ;;        # unset (SSH, headless): gnome-shell on PATH decides
    *GNOME*) return 0 ;;
    *) return 1 ;;         # a set desktop without GNOME (KDE, XFCE) wins
  esac
}
