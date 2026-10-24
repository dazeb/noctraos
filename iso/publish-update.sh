#!/usr/bin/env bash
# publish-update.sh — publish a rolling NoctraOS update (not an ISO) to the update channels.
#
#   iso/publish-update.sh nightly [--ref REF] [--notes TEXT] [--relogin] [--reboot] [--flavour F]
#       build a bundle of REF (default origin/main) as the next serial and publish it on the nightly channel
#   iso/publish-update.sh stable --rollout PCT [--from nightly|stable] [--notes TEXT] [--flavour F]
#       promote the newest nightly (or widen/renew the current stable) to PCT percent of machines: same
#       bundle, same serial, a fresh signature and expiry. 10 -> 50 -> 100 over a few days is the usual path.
#   iso/publish-update.sh renew <channel> [--flavour F]
#       re-sign the channel's current manifest with a new expiry (run at least every 2 weeks; manifests last 30 days)
#
# --flavour (default NOCTRAOS_FLAVOUR, else zorin) picks the flavour's own serials, bundles and channels
# (docs/flavours.md): zorin keeps the top-level layout every installed machine already reads, and any other
# flavour lives under its own folder (updates/kubuntu/bundles/, updates/kubuntu/<channel>/). A machine takes
# only manifests of its own flavour, so the two never cross.
#
# Layout in each store:  updates/[<flavour>/]bundles/noctraos-N.tar.gz  (immutable, never overwritten)
#                        updates/[<flavour>/]<channel>/manifest.json + manifest.json.sig  (the only mutable files)
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
FLAVOUR="${NOCTRAOS_FLAVOUR:-zorin}"
if [ "$MODE" = renew ]; then CHANNEL="${1:?renew needs a channel}"; shift; FROM="$CHANNEL"; ROLLOUT="keep"; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="$2"; shift ;;
    --rollout) ROLLOUT="$2"; shift ;;
    --from) FROM="$2"; shift ;;
    --notes) NOTES="$2"; shift ;;
    --flavour) FLAVOUR="$2"; shift ;;
    --relogin|--reboot) FLAGS+=("$1") ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
case "$CHANNEL" in nightly|stable) ;; *) die "channel must be nightly or stable" ;; esac
case "$FROM" in ""|nightly|stable) ;; *) die "source channel must be nightly or stable" ;; esac
case "$FLAVOUR" in
  zorin) PREFIX="" ;;                 # the layout that predates flavours: updates/bundles/, updates/<channel>/
  kubuntu) PREFIX="$FLAVOUR/" ;;
  *) die "flavour must be zorin or kubuntu, not $FLAVOUR" ;;
esac
[ -r "$KEY" ] || die "no signing key at $KEY (set NOCTRAOS_UPDATE_KEY)"
[ -r "$SIGNERS" ] || die "missing $SIGNERS"
if [ "$CHANNEL" = stable ]; then
  : "${FROM:=nightly}"
  [[ "$ROLLOUT" =~ ^([0-9]|[1-9][0-9]|100|keep)$ ]] || die "stable needs --rollout 0..100"
fi
[ "$CHANNEL" = nightly ] && [ "$MODE" = nightly ] && [ -z "$ROLLOUT" ] && ROLLOUT=100

# One publish at a time on this workstation: two jobs choosing "the next serial" together would race for the same number.
# (The CI update jobs, the rolling nightly timer and a manual run all come through here.)
exec 9>"${UPDATE_PUBLISH_LOCK:-${XDG_RUNTIME_DIR:-/tmp}/noctraos-update-publish.lock}"
flock -n 9 || die "another update publish is running on this computer; wait for it and try again"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/out"

# ---- 1. decide the serial and the source manifest ---------------------------------------------------
# Only this flavour's manifests are read: serials, bundles and channels are per flavour (docs/flavours.md).
for s in $STORES; do
  for c in nightly stable; do
    f="$WORK/seen-$s-$c.json"
    ( export RELEASE_STORE="$s"; store_env; rclone cat "$STORE_REMOTE:$STORE_BUCKET/updates/$PREFIX$c/manifest.json" > "$f" 2>/dev/null ) || rm -f "$f"
  done
done
shopt -s nullglob
SEEN_FILES=("$WORK"/seen-*.json)
shopt -u nullglob
for f in "${SEEN_FILES[@]}"; do
  python3 - "$f" "$FLAVOUR" "$PREFIX" <<'PY' || die "invalid source manifest: $f"
import json, sys
source = json.load(open(sys.argv[1]))
flavour, prefix = sys.argv[2:]
if source.get('flavour', 'zorin') != flavour:
    sys.exit(f'source is for {source.get("flavour", "zorin")}, not {flavour}')
if source['bundle']['path'] != f'{prefix}bundles/noctraos-{source["serial"]}.tar.gz':
    sys.exit('source bundle path does not match the flavour and serial')
PY
done

if [ "$MODE" = nightly ]; then
  SERIAL="$("${MAKE[@]}" serial "${SEEN_FILES[@]}")"
  NEXT_SERIAL="$SERIAL"; RETRY_SOURCE=""
  COMMIT="$(git -C "${NOC_UPDATE_REPO:-$ROOT}" rev-parse --verify "$REF^{commit}")"
  for s in $STORES; do
    f="$WORK/seen-$s-nightly.json"; [ -s "$f" ] || continue
    retry="$(python3 - "$f" "$COMMIT" "$SERIAL" <<'PY'
import json, sys
source = json.load(open(sys.argv[1]))
if source.get('commit') == sys.argv[2] and source['serial'] == int(sys.argv[3]) - 1:
    print(source['serial'])
PY
)"
    if [ -n "$retry" ]; then SERIAL="$retry"; RETRY_SOURCE="$f"; break; fi
  done
  log "building update $SERIAL for $FLAVOUR from $REF"
  "${MAKE[@]}" bundle --ref "$REF" --serial "$SERIAL" --flavour "$FLAVOUR" --out "$WORK/out" >/dev/null
  if [ -n "$RETRY_SOURCE" ] && ! python3 - "$RETRY_SOURCE" "$WORK/out/bundle.json" <<'PY'
import json, sys
source, built = (json.load(open(p)) for p in sys.argv[1:])
sys.exit(0 if source['bundle']['sha256'] == built['sha256'] else 1)
PY
  then
    # A newer builder may filter an older commit differently. Its old published bundle stays immutable.
    SERIAL="$NEXT_SERIAL"
    log "bundle construction changed: building the next immutable update $SERIAL"
    "${MAKE[@]}" bundle --ref "$REF" --serial "$SERIAL" --flavour "$FLAVOUR" --out "$WORK/out" >/dev/null
  fi
  MANIFEST_ARGS=(--bundle-json "$WORK/out/bundle.json")
else
  SRC=""
  for s in $STORES; do [ -s "$WORK/seen-$s-$FROM.json" ] && { SRC="$WORK/seen-$s-$FROM.json"; break; }; done
  [ -n "$SRC" ] || die "no $FLAVOUR $FROM manifest found in any store: nothing to publish from"
  # take the highest serial any store has for the source channel
  best=0
  for s in $STORES; do
    f="$WORK/seen-$s-$FROM.json"; [ -s "$f" ] || continue
    read -r n percent < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["serial"], m["rollout"]["percent"])' "$f")
    if [ "$n" -gt "$best" ] || { [ "$n" -eq "$best" ] && [ "$percent" -gt "${best_percent:-0}" ]; }; then
      best="$n"; best_percent="$percent"; SRC="$f"
    fi
  done
  SERIAL="$best"
  if [ "$ROLLOUT" = keep ]; then ROLLOUT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["rollout"]["percent"])' "$SRC")"; fi
  log "publishing update $SERIAL for $FLAVOUR from the $FROM channel to $CHANNEL at $ROLLOUT%"
  MANIFEST_ARGS=(--from-manifest "$SRC")
  # the bundle is already in the stores; fetch it so every store can be topped up
  mkdir -p "$WORK/out/${PREFIX}bundles"
  for s in $STORES; do
    if ( export RELEASE_STORE="$s"; store_env; rclone copyto "$STORE_REMOTE:$STORE_BUCKET/updates/${PREFIX}bundles/noctraos-$SERIAL.tar.gz" "$WORK/out/${PREFIX}bundles/noctraos-$SERIAL.tar.gz" ) 2>/dev/null; then break; fi
  done
  [ -s "$WORK/out/${PREFIX}bundles/noctraos-$SERIAL.tar.gz" ] || die "bundle $SERIAL is not in any store"
fi
if [ "$CHANNEL" = stable ]; then
  for s in $STORES; do
    f="$WORK/seen-$s-stable.json"; [ -s "$f" ] || continue
    read -r n percent < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["serial"], m["rollout"]["percent"])' "$f")
    [ "$n" -le "$SERIAL" ] || die "$FLAVOUR stable already holds newer update $n: not replacing it with $SERIAL"
    if [ "$n" -eq "$SERIAL" ] && [ "$percent" -gt "$ROLLOUT" ]; then
      ROLLOUT="$percent"
    fi
  done
fi
[ -n "$NOTES" ] && MANIFEST_ARGS+=(--notes "$NOTES")
"${MAKE[@]}" manifest "${MANIFEST_ARGS[@]}" --flavour "$FLAVOUR" --channel "$CHANNEL" --rollout "$ROLLOUT" --key "$KEY" --out "$WORK/out" "${FLAGS[@]}" >/dev/null
MANIFEST="$WORK/out/${PREFIX}$CHANNEL/manifest.json"
BUNDLE="$WORK/out/${PREFIX}bundles/noctraos-$SERIAL.tar.gz"
WANT_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["bundle"]["sha256"])' "$MANIFEST")"
echo "$WANT_SHA  $BUNDLE" | sha256sum -c - >/dev/null || die "bundle does not hash to the manifest"

# ---- 2. bundles first, in every store; never overwrite ------------------------------------------------
for s in $STORES; do
  ( export RELEASE_STORE="$s"; store_env
    dest="$STORE_REMOTE:$STORE_BUCKET/updates/${PREFIX}bundles/noctraos-$SERIAL.tar.gz"
    listing="$(rclone lsf --format 'ps' --separator '|' "$STORE_REMOTE:$STORE_BUCKET/updates/${PREFIX}bundles/")" \
      || { echo "could not list $s (credentials or network): not publishing blind" >&2; exit 1; }
    have="$(awk -F'|' -v n="noctraos-$SERIAL.tar.gz" '$1 == n {print $2}' <<<"$listing")"
    if [ -n "$have" ]; then
      got="$(rclone cat "$dest" | sha256sum | cut -d' ' -f1)"
      [ "$got" = "$WANT_SHA" ] || { echo "$s already holds a DIFFERENT bundle $SERIAL: not overwriting" >&2; exit 1; }
      echo "$s: bundle $SERIAL already there"
    else
      log "$s: uploading bundle $SERIAL"
      rclone copyto "$BUNDLE" "$dest" --s3-no-check-bucket \
        --header-upload "Cache-Control: public, max-age=31536000, immutable"
    fi ) || exit 1
done

# ---- 3. then the manifests (a client that reads between the two files retries once, see noc-selfupdate) ----
for s in $STORES; do
  ( export RELEASE_STORE="$s"; store_env
    log "$s: publishing the $FLAVOUR $CHANNEL manifest"
    for f in manifest.json manifest.json.sig; do
      rclone copyto "$WORK/out/${PREFIX}$CHANNEL/$f" "$STORE_REMOTE:$STORE_BUCKET/updates/${PREFIX}$CHANNEL/$f" --s3-no-check-bucket \
        --header-upload "Cache-Control: no-cache, max-age=60"
    done ) || exit 1
done

# ---- 4. read back what a client gets, through the public hostname -------------------------------------------
for s in $STORES; do
  ( export RELEASE_STORE="$s"; store_env
    base="$STORE_PUBLIC_BASE/updates"
    curl -sSf --connect-timeout 20 "$base/${PREFIX}$CHANNEL/manifest.json" -o "$WORK/pub.json"
    curl -sSf --connect-timeout 20 "$base/${PREFIX}$CHANNEL/manifest.json.sig" -o "$WORK/pub.sig"
    ssh-keygen -Y verify -f "$SIGNERS" -I release@noctraos.dev -n noctraos-update -s "$WORK/pub.sig" < "$WORK/pub.json" >/dev/null \
      || { echo "FAIL: the $CHANNEL manifest read back from $s does not verify with configs/update/update-signers" >&2; exit 1; }
    cmp -s "$WORK/pub.json" "$MANIFEST" || { echo "FAIL: the public manifest on $s differs from what was published" >&2; exit 1; }
    : > "$WORK/pub.tgz"
    for _try in 1 2 3 4 5; do
      curl -sSfL -C - --connect-timeout 20 -o "$WORK/pub.tgz" "$base/${PREFIX}bundles/noctraos-$SERIAL.tar.gz" && break || sleep "${VERIFY_RETRY_DELAY:-5}"
    done
    echo "$WANT_SHA  $WORK/pub.tgz" | sha256sum -c - >/dev/null || { echo "FAIL: bundle $SERIAL from $s hashes wrong" >&2; exit 1; }
    echo "OK  $s: $base/${PREFIX}$CHANNEL (update $SERIAL, $FLAVOUR, $ROLLOUT%)" ) || exit 1
done
log "published update $SERIAL on the $FLAVOUR $CHANNEL ($ROLLOUT%) to: $STORES"
