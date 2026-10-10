#!/usr/bin/env bash
# Module 11: Hermes Desktop, preinstalled. The launcher entry, icon, wrapper and
# onboarding prompt ship with module 06; this builds the runtime + app so the first click just opens it.
# Warn-not-die: the launcher falls back to installing on first use.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

log "Hermes Desktop — free Nous tier primary, local Ollama fallback"

if as_user /usr/local/bin/noctraos-hermes install; then
  log "OK: Hermes Desktop ready (launch from the Agents menu)"
else
  warn "Hermes Desktop install did not finish — clicking Hermes will retry it"
fi

# Hermes now exists: link the NoctraOS skill into it (module 07 ran before ~/.hermes did). Idempotent, never fatal.
as_user /usr/local/bin/noc-agent-skills install || warn "Could not link the NoctraOS agent skill for Hermes (noc agent-skills install retries)"
