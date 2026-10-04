#!/usr/bin/env bash
# Module 11: Hermes Desktop, preinstalled. The launcher entry and icon ship with
# module 06; this builds the runtime + app so the first click just opens it.
# Warn-not-die: the launcher falls back to installing on first use.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

log "Hermes Desktop — free Nous tier primary, local Ollama fallback"

sudo install -m 755 "$REPO_ROOT/bin/noctraos-hermes" /usr/local/bin/noctraos-hermes

if as_user /usr/local/bin/noctraos-hermes install; then
  log "OK: Hermes Desktop ready (launch from the Agents menu)"
else
  warn "Hermes Desktop install did not finish — clicking Hermes will retry it"
fi
