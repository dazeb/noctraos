#!/usr/bin/env bash
# nightly-update.sh — make the nightly update channel truly rolling: publish GitHub main when it changed and its checks pass.
#
#   iso/nightly-update.sh [--dry-run]
#
# Runs daily from a systemd user timer (iso/setup-nightly-update.sh) on the release workstation, the only machine with the signing
# key. It uses its OWN clone of GitHub main (~/.local/share/noctraos-nightly/repo, reset to origin/main before every run), so it
# never depends on a development checkout. A run
#   1. does nothing when no file that goes into an update changed since the update the nightly channel serves now (a site or docs
#      only commit does not spend a serial: the list of paths is `make-update.py items`);
#   2. runs the unit tests and the theme check on that commit, and stops, with a desktop notification, when they fail;
#   3. publishes it with iso/publish-update.sh nightly, notes "Nightly YYYY-MM-DD <short sha>: <subject>".
# It only ever writes the nightly channel. Nightly is for testers who chose it in the Updates page; moving an update to stable is a
# deliberate step (a tag, or iso/publish-update.sh stable), never automatic.
# Environment (tests set these): NIGHTLY_HOME, NIGHTLY_REPO_URL, NIGHTLY_PUBLIC_BASE, PUBLISH_UPDATE, NIGHTLY_CHECKS.
set -Eeuo pipefail

HOME_DIR="${NIGHTLY_HOME:-$HOME/.local/share/noctraos-nightly}"
REPO_URL="${NIGHTLY_REPO_URL:-https://github.com/dazeb/noctraos.git}"
BASE="${NIGHTLY_PUBLIC_BASE:-https://dl.noctraos.dev/updates}"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
log() { printf '=== %s %s\n' "$(date '+%F %H:%M')" "$*"; }

notify_failure() {
  log "FAILED: $1"
  command -v notify-send >/dev/null 2>&1 && notify-send --urgency=critical --app-name=NoctraOS \
    "The NoctraOS nightly update was not published" "$1" || true
}

mkdir -p "$HOME_DIR"
exec 8>"$HOME_DIR/lock"
flock -n 8 || { log "another nightly run is in progress"; exit 0; }

REPO="$HOME_DIR/repo"
[ -d "$REPO/.git" ] || git clone -q "$REPO_URL" "$REPO"
git -C "$REPO" fetch -q origin main
git -C "$REPO" reset -q --hard origin/main
head="$(git -C "$REPO" rev-parse HEAD)"

# What the nightly channel serves now. No manifest yet (or an unreachable host) means: publish.
published="$(curl -fsS --max-time 30 "$BASE/nightly/manifest.json" 2>/dev/null | jq -r '.commit // empty' 2>/dev/null || true)"
if [ "$published" = "$head" ]; then log "the nightly channel already serves ${head:0:7}"; exit 0; fi
mapfile -t items < <(python3 "$REPO/scripts/make-update.py" items)
if [ -n "$published" ] && git -C "$REPO" cat-file -e "$published^{commit}" 2>/dev/null \
   && git -C "$REPO" diff --quiet "$published" "$head" -- "${items[@]}"; then
  log "main moved (${published:0:7} to ${head:0:7}) but nothing an update carries changed: no new update"
  exit 0
fi

checks="${NIGHTLY_CHECKS:-}"
if [ -z "$checks" ]; then
  checks='python3 -B -m unittest discover -s tests && python3 -B scripts/render-theme.py --check'
fi
log "checking ${head:0:7}"
if ! ( cd "$REPO" && bash -c "$checks" ) > "$HOME_DIR/checks.log" 2>&1; then
  notify_failure "main (${head:0:7}) fails its checks, so it was not published. See $HOME_DIR/checks.log."
  exit 1
fi

notes="Nightly $(date -u +%F) ${head:0:7}: $(git -C "$REPO" log -1 --format=%s "$head" | cut -c1-120)"
if [ "$DRY" = 1 ]; then log "dry run: would publish ${head:0:7} as: $notes"; exit 0; fi
log "publishing: $notes"
if ! bash "${PUBLISH_UPDATE:-$REPO/iso/publish-update.sh}" nightly --ref "$head" --notes "$notes"; then
  notify_failure "publish-update.sh failed for ${head:0:7}."
  exit 1
fi
log "published ${head:0:7} on the nightly channel"
