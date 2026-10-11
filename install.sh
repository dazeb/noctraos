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

# ---- flavour (docs/flavours.md) ------------------------------------------------
# Given explicitly on a machine that has no flavour file yet, module 07 records it there.
NOCTRAOS_FLAVOUR_GIVEN="${NOCTRAOS_FLAVOUR:+1}"
NOCTRAOS_FLAVOUR="$(noctraos_flavour)" || exit 1
export NOCTRAOS_FLAVOUR NOCTRAOS_FLAVOUR_GIVEN

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
log "Flavour: $NOCTRAOS_FLAVOUR"

run_module() {
  log "───────────────────── $1 ─────────────────────"
  bash "$REPO_ROOT/install/$1"
}

# Re-run a single module (e.g. to retry a flaky download, or the optional local AI step: optional/local_llm.sh)
# with the full environment set up above, then stop.
if [ -n "$ONLY" ]; then
  if [ -f "$REPO_ROOT/install/$ONLY" ]; then
    run_module "$ONLY"
  elif [ -f "$REPO_ROOT/install/desktop/$(flavour_desktop)/$ONLY" ]; then
    run_desktop_module "$ONLY"      # a bare name of this flavour's desktop module, e.g. 09_super_search.sh
  else
    die "no such module: install/$ONLY (nor install/desktop/$(flavour_desktop)/$ONLY)"
  fi
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
run_desktop_module 01_desktop_packages.sh
run_module 02_mise.sh

# Local AI (GPU stack, Ollama, LLMFIT) is optional and runs later: `noc llm setup`. No model is downloaded by this installer.
# Hermes Desktop (about 5 GB, a 25 to 40 minute build) is optional too: `noc hermes setup`, or the Control Panel's Apps page.

if [ "$SKIP_GUI" -eq 1 ]; then
  log "SKIP 04/04b/04c/04d/05/06/08/09/10 (--skip-gui)"
else
  run_module 04_gui_apps.sh
  run_module 04_workstation_apps.sh
  run_desktop_module 04_desktop_apps.sh
  run_module 04c_app_policy.sh
  # Non-core: a flaky GitHub download must not abort onboarding.
  run_module 04d_appmanager.sh \
    || warn "AppManager install did not complete — continuing. Retry: bash ~/.local/share/noctraos/install.sh --only 04d_appmanager.sh"
  run_desktop_module 05_mouse_ergonomics.sh
  run_desktop_module 06_desktop_theme.sh
  run_desktop_module 08_shell_theme.sh
  run_desktop_module 09_super_search.sh
  run_module 10_boot_theme.sh
fi

run_module 07_persistence.sh

log "✔ Install complete. Full log: $LOG_FILE"
log "Local AI is optional and not set up yet: noc llm setup (then noc llm fit to find a model that fits)."
log "Hermes Desktop is optional and not set up yet: noc hermes setup (about 5 GB, 25 to 40 minutes), or the Control Panel's Apps page."
log "Health check anytime with: noc doctor"
