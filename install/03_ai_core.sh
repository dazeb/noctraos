#!/usr/bin/env bash
# Module 03: local AI engine — Ollama daemon + baseline model.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

MODEL="${NOCTRAOS_MODEL:-qwen2.5-coder:7b}"
EMBED_MODEL="${NOCTRAOS_EMBED_MODEL:-nomic-embed-text}"
log "Local AI engine — default model: $MODEL, embedding model: $EMBED_MODEL"

if have ollama; then
  log "OK: Ollama already installed ($(ollama --version 2>/dev/null | head -n 1))"
else
  log "Installing Ollama (official installer)..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

if systemctl is-enabled --quiet ollama 2>/dev/null; then
  log "OK: ollama.service enabled"
else
  sudo systemctl enable ollama
fi
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

if curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags \
    | jq -e --arg m "$MODEL" '.models[]? | select(.name == $m or .name == ($m + ":latest"))' >/dev/null 2>&1; then
  log "OK: model $MODEL already present"
else
  log "Pulling model $MODEL — multi-GB download, be patient..."
  ollama pull "$MODEL"
fi

# Small embedding model for RAG / semantic search — cheap to keep around.
if curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags \
    | jq -e --arg m "$EMBED_MODEL" '.models[]? | select(.name == $m or .name == ($m + ":latest"))' >/dev/null 2>&1; then
  log "OK: embedding model $EMBED_MODEL already present"
else
  log "Pulling embedding model $EMBED_MODEL (small download)..."
  ollama pull "$EMBED_MODEL"
fi

log "AI core complete. Endpoint: http://localhost:11434"
