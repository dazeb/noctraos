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
