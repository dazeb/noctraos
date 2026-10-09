#!/usr/bin/env bash
# Module 00: preflight — validate the environment before any mutation.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

log "Checking execution context..."
if [ "$(id -u)" -eq 0 ] && [ -z "${SUDO_USER:-}" ]; then
  die "Run the installer as your normal desktop user (sudo is used internally), not as root."
fi
if ! sudo -n true 2>/dev/null; then
  # No cached/NOPASSWD credentials — fall back to an interactive prompt (needs a TTY).
  if ! sudo -v 2>/dev/null; then
    die "This installer needs sudo privileges (headless runs require passwordless sudo or cached credentials)."
  fi
fi
log "OK: running as '$TARGET_USER' with sudo"

log "Checking operating system..."
if [ ! -r /etc/os-release ]; then
  die "Cannot read /etc/os-release — not an Ubuntu-based system?"
fi
# shellcheck source=/dev/null
. /etc/os-release
os_ok=0
case "${ID:-}" in
  zorin|ubuntu) os_ok=1 ;;
  *)
    case "${ID_LIKE:-}" in
      *ubuntu*|*debian*) os_ok=1 ;;
    esac ;;
esac
if [ "$os_ok" -ne 1 ]; then
  die "Unsupported OS: ${PRETTY_NAME:-unknown}. Zorin OS or an Ubuntu-based system is required."
fi
log "OK: ${PRETTY_NAME:-$ID}"

log "Checking network..."
net_ok=0
if curl -fsSI --max-time 10 -o /dev/null https://archive.ubuntu.com/ubuntu/ \
   || curl -fsSI --max-time 10 -o /dev/null http://archive.ubuntu.com/ubuntu/; then
  log "OK: Ubuntu archive reachable"
  net_ok=1
else
  warn "archive.ubuntu.com unreachable"
fi
if curl -fsSI --max-time 10 -o /dev/null https://flathub.org/; then
  log "OK: Flathub reachable"
else
  warn "flathub.org unreachable — Flatpak app installs will fail"
fi
if [ "$net_ok" -ne 1 ] && ! curl -fsSI --max-time 10 -o /dev/null https://github.com/; then
  die "No usable internet connection. Connect to the internet and re-run."
fi

log "Checking disk space..."
avail_gb="$(df -BG --output=avail / | tail -n 1 | tr -dc '0-9')"
# A fresh install needs room for the models and runtimes. A machine that already finished
# first-boot provisioning is only updating, so it needs far less.
min_gb=25
if [ -f "$TARGET_HOME/.local/share/noctraos/.provisioned" ]; then
  min_gb=8
fi
if [ "$avail_gb" -lt "$min_gb" ]; then
  # A virtual disk enlarged after install leaves the new space outside the system partition, so "18GiB free" on a
  # 64 GB disk is baffling. This runs before the Control Panel exists, in the terminal first boot opened (sudo is
  # already unlocked), so offer the fix right here. Nothing changes without a yes.
  unused_gb=0 needs_fdisk=false
  if [ -f "$REPO_ROOT/bin/noc-disk" ] && disk_json="$(python3 "$REPO_ROOT/bin/noc-disk" status --json 2>/dev/null)"; then
    read -r unused_gb needs_fdisk < <(printf '%s' "$disk_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d["expandable_bytes"]/2**30) if d.get("can_grow") else 0, "true" if d.get("needs_fdisk") else "false")' 2>/dev/null || echo "0 false")
  fi
  if [ "${unused_gb:-0}" -gt 0 ]; then
    warn "The disk has ${unused_gb}GiB that the system is not using yet (the disk was made bigger after install)."
    if [ -t 0 ]; then
      # Same disclosure as the Control Panel's dialog (which does not exist yet on this path): growing needs the sfdisk tool.
      if [ "$needs_fdisk" = true ]; then
        printf '  It first installs a small partition tool (fdisk) from the Ubuntu archive, which needs the internet and\n'
        printf '  also updates a few system libraries that go with it.\n'
      fi
      printf '  Use all of it now? Your files are not touched and nothing is erased. [Y/n] '
      read -r reply || reply=n
      case "${reply:-Y}" in
        [Yy]*|"")
          if sudo python3 "$REPO_ROOT/bin/noc-disk" grow; then
            avail_gb="$(df -BG --output=avail / | tail -n 1 | tr -dc '0-9')"
          else
            rc=$?
            [ "$rc" -eq 10 ] && die "Restart the computer so the system sees the bigger disk, then run this setup again."
          fi ;;
      esac
    else
      warn "Open the NoctraOS Control Panel, choose Hardware, then Use all the disk space. After that, run this setup again."
    fi
  fi
  if [ "$avail_gb" -lt "$min_gb" ]; then
    die "Only ${avail_gb}GiB free on / — ${min_gb}GiB minimum (AI models + language runtimes)."
  fi
fi
log "OK: ${avail_gb}GiB free on /"

ram_gb="$(free -g | awk 'NR==2 {print $2}')"
if [ "$ram_gb" -lt 8 ]; then
  warn "Only ~${ram_gb}GiB RAM — running 7B-class models locally needs 8GiB minimum (16GiB recommended). Ollama will otherwise swap heavily."
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  warn "No graphical session visible from this shell — desktop settings are applied via the user session bus and should still work."
fi

log "Preflight complete."
