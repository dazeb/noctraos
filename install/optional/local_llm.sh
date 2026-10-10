#!/usr/bin/env bash
# Optional module: local AI — the GPU compute stack, the Ollama engine and LLMFIT (which finds the models that fit this
# computer). It is NOT part of the first-run install. Run it later with `noc llm setup`, which calls this file through
# install.sh --only. It downloads the engine and the finder only: no model. Choose one with `noc llm fit`, then pull it
# with `noc models pull <name>`.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

ram_gb="$(free -g | awk 'NR==2 {print $2}')"
if [ "$ram_gb" -lt 8 ]; then
  warn "Only ~${ram_gb}GiB RAM — local models need 8GiB at least (16GiB recommended). Ollama will otherwise swap heavily."
fi

# GPU drivers + CUDA/ROCm come before Ollama, so Ollama finds a working GPU. A failure must not block the engine:
# it can be repeated later with `noc gpu install`.
log "GPU compute stack (NVIDIA → driver + CUDA, AMD → ROCm)..."
bash "$REPO_ROOT/bin/noc-gpu" install \
  || warn "GPU setup did not complete — continuing. Retry later with: noc gpu install"

# The vendor installer turns the service on at boot. That is the person's choice, not ours: a first install leaves it off,
# and a re-run keeps whatever was chosen (ollama_boot_choice in lib.sh).
boot_choice="$(ollama_boot_choice)"
if have ollama; then
  log "OK: Ollama already installed ($(ollama --version 2>/dev/null | head -n 1))"
else
  log "Installing Ollama (official installer)..."
  curl -fsSL https://ollama.com/install.sh | sh
fi
ollama_boot_restore "$boot_choice"

if systemctl is-active --quiet ollama 2>/dev/null; then
  log "OK: ollama.service already running"
else
  sudo systemctl start ollama
fi

log "Waiting for the Ollama API on 127.0.0.1:11434 (localhost-only)..."
api_up=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    api_up=1
    break
  fi
  sleep 2
done
if [ "$api_up" -ne 1 ]; then
  die "Ollama API did not come up. Inspect with: journalctl -u ollama -n 50"
fi
log "OK: Ollama API healthy on 127.0.0.1:11434"

# LLMFIT reads this computer's RAM, CPU and GPU and lists the models that fit (`noc llm fit`). The PyPI package ships the
# llmfit binary; pipx puts it in this account's own ~/.local/bin, so it needs no root and is removed with `pipx uninstall`.
if [ -x "$TARGET_HOME/.local/bin/llmfit" ]; then
  log "OK: LLMFIT already installed"
else
  log "Installing LLMFIT (finds the models that fit this computer) for $TARGET_USER..."
  have pipx || apt_install pipx
  as_user pipx install llmfit
fi

if [ -f /var/run/reboot-required.pkgs ] && grep -x 'noctraos-gpu' /var/run/reboot-required.pkgs >/dev/null; then
  warn "REBOOT REQUIRED: the GPU driver was installed and loads on next boot. Local models run on the CPU until then."
fi
log "Local AI engine ready. No model is installed yet."
if [ "$boot_choice" = on ]; then
  log "Ollama starts with this computer (your choice). Change it: noc llm autostart off"
else
  log "Ollama is running now, and does not start with this computer unless you ask it to: noc llm autostart on (or AI models in the Control Panel)"
fi
log "Find one that fits this computer: noc llm fit — then pull it with: noc models pull <name>"
