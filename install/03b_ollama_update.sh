#!/usr/bin/env bash
# Module 03b: bring Ollama up to the newest upstream release.
# Not part of a normal install (`noc llm setup` installs Ollama, optional/local_llm.sh); run it with `install.sh --only 03b_ollama_update.sh`, or from the
# Control Panel's Apps page through noc-privileged. Idempotent: it does nothing when Ollama is already on the latest release.
# The newest release is read from GitHub Releases (bin/noc-upstream), and the vendor's installer is pinned to exactly that
# version (OLLAMA_VERSION), so "latest" is decided here, not by whatever the installer's default happens to be.
# It restarts the Ollama service, which unloads any model that is running.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

have ollama || die "Ollama is not installed (noc llm setup installs it)"
have jq || die "jq is missing"

row="$(python3 "$REPO_ROOT/bin/noc-upstream" list --json --refresh | jq -c '.apps[] | select(.id == "ollama")')" \
  || die "could not read the upstream release information"
status="$(jq -r .status <<<"$row")"
installed="$(jq -r .installed <<<"$row")"
latest="$(jq -r .latest <<<"$row")"

case "$status" in
  current) log "OK: Ollama $installed is already the latest release"; exit 0 ;;
  outdated) ;;
  *) die "cannot tell whether Ollama needs an update (status: $status; no network or GitHub rate limit?): nothing was changed" ;;
esac

log "Updating Ollama $installed -> $latest (official installer, pinned to that release; the service restarts)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 3 --max-time 60 https://ollama.com/install.sh -o "$tmp/install.sh"
sudo env OLLAMA_VERSION="$latest" sh "$tmp/install.sh"

now="$(python3 "$REPO_ROOT/bin/noc-upstream" list --json | jq -r '.apps[] | select(.id == "ollama") | .installed')"
[ "$now" = "$latest" ] || die "Ollama reports $now after the update, expected $latest"
log "OK: Ollama is now $now"
