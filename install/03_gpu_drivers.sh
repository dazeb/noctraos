#!/usr/bin/env bash
# Module 03: GPU drivers for local models — NVIDIA (driver + CUDA) and AMD (amdgpu + ROCm).
# Runs BEFORE 03_ai_core.sh on purpose: Ollama's installer looks for nvidia-smi / an AMD
# GPU at install time and only then fetches (or skips) its CUDA / ROCm runtime.
# Ollama bundles its own CUDA runtime, so the driver is all it needs; the full CUDA
# toolkit (nvcc) is opt-in: NOCTRAOS_CUDA_TOOLKIT=1.
# GPU setup is warn-not-die: a machine without a usable GPU still gets a working CPU install.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

# lspci prints "[vendor:device]"; drain the pipe fully (no grep -q under pipefail).
gpu_vendor_present() {
  lspci -nn 2>/dev/null | awk -v v="[$1:" '/VGA|3D|Display/ && index($0, v) {f=1} END {exit !f}'
}

pkg_installed() {
  dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' "$1" 2>/dev/null \
    | awk '$1 == "ii" {f=1} END {exit !f}'
}

if ! have lspci; then
  apt_install pciutils || warn "could not install pciutils — skipping GPU detection"
fi
if ! have lspci; then
  warn "lspci unavailable — GPU drivers skipped"
  exit 0
fi

NEED_REBOOT=0

# ---- NVIDIA ------------------------------------------------------------------------
if gpu_vendor_present 10de; then
  log "NVIDIA GPU detected"
  if pkg_installed 'nvidia-driver-*'; then
    log "OK: NVIDIA driver package already installed"
  else
    log "Installing the recommended NVIDIA driver (ubuntu-drivers)..."
    apt_install ubuntu-drivers-common || warn "ubuntu-drivers-common failed to install"
    if sudo ubuntu-drivers install; then
      NEED_REBOOT=1
    else
      warn "NVIDIA driver install failed — Ollama will run on CPU. Retry: sudo ubuntu-drivers install"
    fi
    if have mokutil && mokutil --sb-state 2>/dev/null | awk '/enabled/ {f=1} END {exit !f}'; then
      warn "Secure Boot is on: at the next boot choose 'Enroll MOK' and enter the password you are prompted for, or the NVIDIA module will not load."
    fi
  fi
  if [ "${NOCTRAOS_CUDA_TOOLKIT:-0}" = "1" ]; then
    if pkg_installed nvidia-cuda-toolkit; then
      log "OK: CUDA toolkit already installed"
    else
      log "Installing the CUDA toolkit (nvcc) — large download..."
      apt_install nvidia-cuda-toolkit || warn "CUDA toolkit install failed"
    fi
  fi
else
  log "SKIP NVIDIA: no NVIDIA GPU found"
fi

# ---- AMD ---------------------------------------------------------------------------
# The amdgpu kernel driver ships in the Ubuntu kernel; Ollama's installer adds the ROCm
# runtime when it sees an AMD GPU. The user needs render/video group access to use it.
if gpu_vendor_present 1002; then
  log "AMD GPU detected"
  if modinfo amdgpu >/dev/null 2>&1; then
    log "OK: amdgpu kernel driver available"
  else
    warn "amdgpu kernel module not found — update the kernel (sudo apt full-upgrade) for AMD GPU support"
  fi
  for grp in render video; do
    if id -nG "$TARGET_USER" | tr ' ' '\n' | awk -v g="$grp" '$0 == g {f=1} END {exit !f}'; then
      log "OK: $TARGET_USER is in group $grp"
    else
      sudo usermod -aG "$grp" "$TARGET_USER" || warn "could not add $TARGET_USER to $grp"
      NEED_REBOOT=1
    fi
  done
else
  log "SKIP AMD: no AMD GPU found"
fi

if [ "$NEED_REBOOT" -eq 1 ]; then
  warn "GPU setup changed — reboot once so the driver loads. Ollama uses the GPU after that (check with: zom doctor)."
fi
log "GPU drivers complete"
