#!/usr/bin/env bash
# noctraos — main orchestrator.
# Run as your normal desktop user; sudo is used internally for system changes.
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${NOCTRAOS_LOG:-/tmp/noctraos-install-$(date +%Y%m%d-%H%M%S).log}"
exec > >(tee -a "$LOG_FILE") 2>&1

# ---- resolve the target desktop user -----------------------------------------
if [ "$(id -u)" -eq 0 ]; then
  TARGET_USER="${SUDO_USER:-}"
  if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
    echo "ERROR: do not run as bare root. Run as your normal desktop user: bash install.sh" >&2
    exit 1
  fi
else
  TARGET_USER="$(id -un)"
fi
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
export REPO_ROOT TARGET_USER TARGET_UID TARGET_HOME

# shellcheck source=install/lib.sh
source "$REPO_ROOT/install/lib.sh"

# ---- flags ---------------------------------------------------------------------
SKIP_GUI=0
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-gui) SKIP_GUI=1 ;;
    --only)     [ $# -ge 2 ] || die "--only needs a module file name, e.g. --only 04d_appmanager.sh"
                ONLY="$2"; shift ;;
    *) die "Unknown option: $1 (supported: --skip-gui --only <module>)" ;;
  esac
  shift
done

echo "======================================================"
echo "  NoctraOS :: AI-first developer workstation"
echo "======================================================"
log "Log file: $LOG_FILE"
log "Target user: $TARGET_USER ($TARGET_HOME)"

run_module() {
  log "───────────────────── $1 ─────────────────────"
  bash "$REPO_ROOT/install/$1"
}

# Re-run a single module (e.g. to retry a flaky download, or the optional local AI step: optional/local_llm.sh)
# with the full environment set up above, then stop.
if [ -n "$ONLY" ]; then
  [ -f "$REPO_ROOT/install/$ONLY" ] || die "no such module: install/$ONLY"
  run_module "$ONLY"
  log "✔ Module $ONLY finished. Full log: $LOG_FILE"
  exit 0
fi

# First, before even the preflight: a VM without its guest agent works, but the host (Proxmox, VMware, ...) cannot show its address or
# shut it down cleanly, so it must not wait for a setup that may stop early (a small disk, no network). A bare-metal machine returns at once.
# Non-core: whatever happens here, the install goes on.
run_module 01b_vm_guest.sh \
  || warn "VM guest tools did not install — continuing. Retry: bash ~/.local/share/noctraos/install.sh --only 01b_vm_guest.sh"
run_module 00_preflight.sh
run_module 01_system.sh
run_module 02_mise.sh

# Local AI (GPU stack, Ollama, LLMFIT) is optional and runs later: `noc llm setup`. No model is downloaded by this installer.

if [ "$SKIP_GUI" -eq 1 ]; then
  log "SKIP 04/04b/04c/04d/05/06/08/09/10/11 (--skip-gui)"
else
  run_module 04_gui_apps.sh
  run_module 04_workstation_apps.sh
  run_module 04c_app_policy.sh
  # Non-core: a flaky GitHub download must not abort onboarding.
  run_module 04d_appmanager.sh \
    || warn "AppManager install did not complete — continuing. Retry: bash ~/.local/share/noctraos/install.sh --only 04d_appmanager.sh"
  run_module 05_mouse_ergonomics.sh
  run_module 06_desktop_theme.sh
  run_module 08_shell_theme.sh
  run_module 09_super_search.sh
  run_module 10_boot_theme.sh
fi

run_module 07_persistence.sh

# Last on purpose: the Hermes build takes 25+ minutes and uses no sudo, so
# anything that needs sudo must run before it. Otherwise the sudo credential
# cache (~15 min) expires and an interactive install stalls on a password prompt.
if [ "$SKIP_GUI" -eq 0 ]; then
  run_module 11_hermes.sh
fi

log "✔ Install complete. Full log: $LOG_FILE"
log "Local AI is optional and not set up yet: noc llm setup (then noc llm fit to find a model that fits)."
log "Health check anytime with: noc doctor"
