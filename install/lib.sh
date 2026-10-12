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

# Ollama's own installer turns the service on at boot, and NoctraOS leaves that choice to the person (docs/what-we-do.md): a
# first install ends with it off, and a later run (an update of Ollama) puts back whatever the person had. Call
# `ollama_boot_choice` BEFORE the vendor installer and `ollama_boot_restore "$choice"` after it. The service may run now;
# the choice is only whether it starts with the computer. Turn it on with `noc llm autostart on` or the AI models page.
ollama_boot_choice() {
  if ! command -v ollama >/dev/null 2>&1 || ! systemctl cat ollama.service >/dev/null 2>&1; then echo off
  elif systemctl is-enabled --quiet ollama.service 2>/dev/null; then echo on
  else echo off
  fi
}

ollama_boot_restore() {
  local now=off
  systemctl is-enabled --quiet ollama.service 2>/dev/null && now=on
  [ "$now" = "$1" ] && return 0
  if [ "$1" = on ]; then sudo systemctl enable ollama.service; else sudo systemctl disable ollama.service; fi
}

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

# noctraos_flavour — this machine's flavour (docs/flavours.md): the flavour file, written once by the ISO or by the first
# install that was given NOCTRAOS_FLAVOUR; else NOCTRAOS_FLAVOUR; else zorin (a machine installed before flavours existed).
# A NOCTRAOS_FLAVOUR that contradicts the file is an error: changing flavour would switch the machine to another update channel.
# The flavour picks the update channel and, later, the desktop modules; desktop_is_gnome stays a guard, never a selector.
noctraos_flavour() {
  local file="${NOCTRAOS_FLAVOUR_FILE:-/etc/noctraos/flavour}" recorded="" wanted="${NOCTRAOS_FLAVOUR:-}"
  [ -r "$file" ] && recorded="$(tr -d '[:space:]' < "$file")"
  if [ -n "$recorded" ] && [ -n "$wanted" ] && [ "$recorded" != "$wanted" ]; then
    die "this machine is the $recorded flavour ($file), but NOCTRAOS_FLAVOUR=$wanted: unset it, or reinstall from the $wanted ISO"
  fi
  local flavour="${recorded:-${wanted:-zorin}}"
  case "$flavour" in
    zorin|kubuntu) printf '%s\n' "$flavour" ;;
    *) die "unknown NoctraOS flavour \"$flavour\" (expected zorin or kubuntu)" ;;
  esac
}

# flavour_desktop — the desktop folder of this machine's flavour under install/desktop/ (zorin: gnome, kubuntu: plasma).
flavour_desktop() {
  case "$(noctraos_flavour)" in
    zorin) printf 'gnome\n' ;;
    kubuntu) printf 'plasma\n' ;;
  esac
}

# run_desktop_module <file> — run install/desktop/<this flavour's desktop>/<file>, or say plainly that this flavour has no
# such module yet (NOT APPLIED, never a success line; docs/flavours.md). Used by install.sh and by core modules that have a
# desktop-specific part, so a core module holds no desktop code of its own.
run_desktop_module() {
  local file="$1" flavour desktop path
  flavour="$(noctraos_flavour)" && desktop="$(flavour_desktop)" || die "cannot tell which flavour this machine is"
  path="$REPO_ROOT/install/desktop/$desktop/$file"
  if [ -f "$path" ]; then
    log "───────────────────── desktop/$desktop/$file ─────────────────────"
    bash "$path"
  else
    warn "NOT APPLIED on the $flavour flavour: $file has no $desktop counterpart yet"
  fi
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

# desktop_is_plasma — success only when KDE Plasma is available as the desktop: plasmashell must exist AND
# XDG_CURRENT_DESKTOP, when set, must name KDE. Plasma-only modules (install/desktop/plasma/) use it to skip honestly
# (NOT APPLIED) on any other desktop, where nothing they write is read.
desktop_is_plasma() {
  have plasmashell || return 1
  case "${XDG_CURRENT_DESKTOP:-}" in
    "") return 0 ;;        # unset (SSH, headless): plasmashell on PATH decides
    *KDE*) return 0 ;;
    *) return 1 ;;
  esac
}
