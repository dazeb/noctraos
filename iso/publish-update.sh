#!/usr/bin/env bash
# publish-update.sh — publish a rolling NoctraOS update (not an ISO) to the update channels.
#
#   iso/publish-update.sh nightly [--ref REF] [--notes TEXT] [--relogin] [--reboot]
#       build a bundle of REF (default origin/main) as the next serial and publish it on the nightly channel
#   iso/publish-update.sh stable --rollout PCT [--from nightly|stable] [--notes TEXT]
#       promote the newest nightly (or widen/renew the current stable) to PCT percent of machines: same
#       bundle, same serial, a fresh signature and expiry. 10 -> 50 -> 100 over a few days is the usual path.
#   iso/publish-update.sh renew <channel>
#       re-sign the channel's current manifest with a new expiry (run at least every 2 weeks; manifests last 30 days)
#
# Layout in each store:  updates/bundles/noctraos-N.tar.gz  (immutable, never overwritten)
#                        updates/<channel>/manifest.json + manifest.json.sig  (the only mutable files)
# Every store in UPDATE_STORES (default "r2 hetzner") gets the same files. All bundles are uploaded before any
# manifest, so a manifest never points at a bundle that is missing somewhere; then each store is read back through its
# PUBLIC hostname and the signature and bundle hash are verified with the same key clients use.
# Signing key: NOCTRAOS_UPDATE_KEY (default ~/secrets/noctraos-update-signing). Never printed, never copied into the repo.
# Credentials and public hosts: iso/r2-env.sh. Design: docs/updates.md.
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# shellcheck source=iso/r2-env.sh
source "$HERE/r2-env.sh"
log() { printf '=== %s %s\n' "$(date +%H:%M)" "$*"; }
die() { echo "publish-update: $*" >&2; exit 1; }

KEY="${NOCTRAOS_UPDATE_KEY:-$HOME/secrets/noctraos-update-signing}"
SIGNERS="${UPDATE_SIGNERS:-$ROOT/configs/update/update-signers}"
STORES="${UPDATE_STORES:-r2 hetzner}"
MAKE=("${PYTHON:-python3}" "$ROOT/scripts/make-update.py")

MODE="${1:-}"; shift || true
case "$MODE" in nightly|stable|renew) ;; *) die "usage: publish-update.sh nightly|stable|renew ... (see the header)" ;; esac
CHANNEL="$MODE"; FROM=""; REF="origin/main"; ROLLOUT=""; NOTES=""; FLAGS=()
if [ "$MODE" = renew ]; then CHANNEL="${1:?renew needs a channel}"; shift; FROM="$CHANNEL"; ROLLOUT="keep"; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="$2"; shift ;;
    --rollout) ROLLOUT="$2"; shift ;;
    --from) FROM="$2"; shift ;;
    --notes) NOTES="$2"; shift ;;
    --relogin|--reboot) FLAGS+=("$1") ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
case "$CHANNEL" in nightly|stable) ;; *) die "channel must be nightly or stable" ;; esac
[ -r "$KEY" ] || die "no signing key at $KEY (set NOCTRAOS_UPDATE_KEY)"
[ -r "$SIGNERS" ] || die "missing $SIGNERS"
if [ "$CHANNEL" = stable ]; then
  : "${FROM:=nightly}"
  [[ "$ROLLOUT" =~ ^([0-9]|[1-9][0-9]|100|keep)$ ]] || die "stable needs --rollout 0..100"
fi
[ "$CHANNEL" = nightly ] && [ "$MODE" = nightly ] && [ -z "$ROLLOUT" ] && ROLLOUT=100

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/out"

# ---- 1. decide the serial and the source manifest ---------------------------------------------------
for s in $STORES; do
  for c in nightly stable; do
    f="$WORK/seen-$s-$c.json"
    ( export RELEASE_STORE="$s"; store_env; rclone cat "$STORE_REMOTE:$STORE_BUCKET/updates/$c/manifest.json" > "$f" 2>/dev/null ) || rm -f "$f"
  done
done
shopt -s nullglob
SEEN_FILES=("$WORK"/seen-*.json)
shopt -u nullglob

if [ "$MODE" = nightly ]; then
  SERIAL="$("${MAKE[@]}" serial "${SEEN_FILES[@]}")"
  log "building update $SERIAL from $REF"
  "${MAKE[@]}" bundle --ref "$REF" --serial "$SERIAL" --out "$WORK/out" >/dev/null
  MANIFEST_ARGS=(--bundle-json "$WORK/out/bundle.json")
else
  SRC=""
  for s in $STORES; do [ -s "$WORK/seen-$s-$FROM.json" ] && { SRC="$WORK/seen-$s-$FROM.json"; break; }; done
  [ -n "$SRC" ] || die "no $FROM manifest found in any store: nothing to publish from"
  # take the highest serial any store has for the source channel
  best=0
  for s in $STORES; do
    f="$WORK/seen-$s-$FROM.json"; [ -s "$f" ] || continue
    n="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["serial"])' "$f")"
    [ "$n" -gt "$best" ] && { best="$n"; SRC="$f"; }
  done
  SERIAL="$best"
  if [ "$ROLLOUT" = keep ]; then ROLLOUT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["rollout"]["percent"])' "$SRC")"; fi
  log "publishing update $SERIAL from the $FROM channel to $CHANNEL at $ROLLOUT%"
  MANIFEST_ARGS=(--from-manifest "$SRC")
  # the bundle is already in the stores; fetch it so every store can be topped up
  mkdir -p "$WORK/out/bundles"
  for s in $STORES; do
    if ( export RELEASE_STORE="$s"; store_env; rclone copyto "$STORE_REMOTE:$STORE_BUCKET/updates/bundles/noctraos-$SERIAL.tar.gz" "$WORK/out/bundles/noctraos-$SERIAL.tar.gz" ) 2>/dev/null; then break; fi
  done
  [ -s "$WORK/out/bundles/noctraos-$SERIAL.tar.gz" ] || die "bundle $SERIAL is not in any store"
fi
[ -n "$NOTES" ] && MANIFEST_ARGS+=(--notes "$NOTES")
"${MAKE[@]}" manifest "${MANIFEST_ARGS[@]}" --channel "$CHANNEL" --rollout "$ROLLOUT" --key "$KEY" --out "$WORK/out" "${FLAGS[@]}" >/dev/null
MANIFEST="$WORK/out/$CHANNEL/manifest.json"
WANT_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["bundle"]["sha256"])' "$MANIFEST")"
echo "$WANT_SHA  $WORK/out/bundles/noctraos-$SERIAL.tar.gz" | sha256sum -c - >/dev/null || die "bundle does not hash to the manifest"

# ---- 2. bundles first, in every store; never overwrite ------------------------------------------------
for s in $STORES; do
  ( export RELEASE_STORE="$s"; store_env
    dest="$STORE_REMOTE:$STORE_BUCKET/updates/bundles/noctraos-$SERIAL.tar.gz"
    listing="$(rclone lsf --format 'ps' --separator '|' "$STORE_REMOTE:$STORE_BUCKET/updates/bundles/")" \
      || { echo "could not list $s (credentials or network): not publishing blind" >&2; exit 1; }
    have="$(awk -F'|' -v n="noctraos-$SERIAL.tar.gz" '$1 == n {print $2}' <<<"$listing")"
    if [ -n "$have" ]; then
      got="$(rclone cat "$dest" | sha256sum | cut -d' ' -f1)"
      [ "$got" = "$WANT_SHA" ] || { echo "$s already holds a DIFFERENT bundle $SERIAL: not overwriting" >&2; exit 1; }
      echo "$s: bundle $SERIAL already there"
    else
      log "$s: uploading bundle $SERIAL"
      rclone copyto "$WORK/out/bundles/noctraos-$SERIAL.tar.gz" "$dest" --s3-no-check-bucket \
        --header-upload "Cache-Control: public, max-age=31536000, immutable"
    fi ) || exit 1
done

# ---- 3. then the manifests (a client that reads between the two files retries once, see noc-selfupdate) ----
for s in $STORES; do
  ( export RELEASE_STORE="$s"; store_env
    log "$s: publishing the $CHANNEL manifest"
    for f in manifest.json manifest.json.sig; do
      rclone copyto "$WORK/out/$CHANNEL/$f" "$STORE_REMOTE:$STORE_BUCKET/updates/$CHANNEL/$f" --s3-no-check-bucket \
        --header-upload "Cache-Control: no-cache, max-age=60"
    done ) || exit 1
done

# ---- 4. read back what a client gets, through the public hostname -------------------------------------------
for s in $STORES; do
  ( export RELEASE_STORE="$s"; store_env
    base="$STORE_PUBLIC_BASE/updates"
    curl -sSf --connect-timeout 20 "$base/$CHANNEL/manifest.json" -o "$WORK/pub.json"
    curl -sSf --connect-timeout 20 "$base/$CHANNEL/manifest.json.sig" -o "$WORK/pub.sig"
    ssh-keygen -Y verify -f "$SIGNERS" -I release@noctraos.dev -n noctraos-update -s "$WORK/pub.sig" < "$WORK/pub.json" >/dev/null \
      || { echo "FAIL: the $CHANNEL manifest read back from $s does not verify with configs/update/update-signers" >&2; exit 1; }
    cmp -s "$WORK/pub.json" "$MANIFEST" || { echo "FAIL: the public manifest on $s differs from what was published" >&2; exit 1; }
    : > "$WORK/pub.tgz"
    for _try in 1 2 3 4 5; do
      curl -sSfL -C - --connect-timeout 20 -o "$WORK/pub.tgz" "$base/bundles/noctraos-$SERIAL.tar.gz" && break || sleep "${VERIFY_RETRY_DELAY:-5}"
    done
    echo "$WANT_SHA  $WORK/pub.tgz" | sha256sum -c - >/dev/null || { echo "FAIL: bundle $SERIAL from $s hashes wrong" >&2; exit 1; }
    echo "OK  $s: $base/$CHANNEL (update $SERIAL, $ROLLOUT%)" ) || exit 1
done
log "published update $SERIAL on $CHANNEL ($ROLLOUT%) to: $STORES"
