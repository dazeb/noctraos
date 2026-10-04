#!/usr/bin/env bash
# Module 02b: GPU compute stack — detect NVIDIA / AMD and install driver + CUDA / ROCm.
# Runs before the AI core so Ollama finds a working GPU. The logic lives in
# bin/noc-gpu so `noc gpu install` can repeat it after hardware changes.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

export TARGET_USER
log "Detecting GPUs (NVIDIA → driver + CUDA, AMD → ROCm)..."
bash "$REPO_ROOT/bin/noc-gpu" install
