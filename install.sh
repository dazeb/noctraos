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
SKIP_AI=0
SKIP_GUI=0
SKIP_GPU=0
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-ai)  SKIP_AI=1 ;;
    --skip-gui) SKIP_GUI=1 ;;
    --skip-gpu) SKIP_GPU=1 ;;
    --only)     [ $# -ge 2 ] || die "--only needs a module file name, e.g. --only 04_appmanager.sh"
                ONLY="$2"; shift ;;
    *) die "Unknown option: $1 (supported: --skip-ai --skip-gui --skip-gpu --only <module>)" ;;
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

# Re-run a single module (e.g. to retry an optional download) with the full
# environment set up above, then stop.
if [ -n "$ONLY" ]; then
  [ -f "$REPO_ROOT/install/$ONLY" ] || die "no such module: install/$ONLY"
  run_module "$ONLY"
  log "✔ Module $ONLY finished. Full log: $LOG_FILE"
  exit 0
fi

run_module 00_preflight.sh
run_module 01_system.sh
run_module 02_mise.sh

# GPU drivers + CUDA/ROCm come before the AI core so Ollama sees a working GPU.
# A failure here (no network to NVIDIA/AMD repos, unsupported kernel…) must not
# block the rest of onboarding — it can be repeated later with `noc gpu install`.
if [ "$SKIP_GPU" -eq 1 ]; then
  log "SKIP 02b_gpu_drivers (--skip-gpu)"
else
  run_module 02b_gpu_drivers.sh \
    || warn "GPU setup did not complete — continuing. Retry later with: noc gpu install"
fi

if [ "$SKIP_AI" -eq 1 ]; then
  log "SKIP 03_ai_core (--skip-ai)"
else
  run_module 03_ai_core.sh
fi

if [ "$SKIP_GUI" -eq 1 ]; then
  log "SKIP 04/04b/04c/05/06/08/09/10/11 (--skip-gui)"
else
  run_module 04_gui_apps.sh
  run_module 04_workstation_apps.sh
  # Non-core: a flaky GitHub download must not abort onboarding.
  run_module 04_appmanager.sh \
    || warn "AppManager install did not complete — continuing. Retry: bash ~/.local/share/noctraos/install.sh --only 04_appmanager.sh"
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
if [ -f /var/run/reboot-required.pkgs ] && grep -x 'noctraos-gpu' /var/run/reboot-required.pkgs >/dev/null; then
  warn "REBOOT REQUIRED: the GPU driver was installed and loads on next boot. Local models run on the CPU until then."
fi
log "Try it: right-click a file in Files → Scripts → 'Ask AI to Explain'."
log "Health check anytime with: noc doctor"
