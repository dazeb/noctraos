#!/usr/bin/env bash
# publish-release.sh — put a built release in the release store (Hetzner Object Storage by default, or the old R2 bucket with RELEASE_STORE=r2) and create the GitHub release.
#
#   iso/publish-release.sh <build-dir>
#   RELEASE_FLAVOURS="zorin kubuntu" iso/publish-release.sh <build-dir>      (default: zorin)
#
# Reads, for each flavour, what iso/build-release.sh wrote: <build-dir>/release/v<VERSION>/ (zorin) and
# <build-dir>/release/v<VERSION>-<flavour>/ (others). Each flavour goes to its own folder in the bucket (docs/flavours.md
# rule 8): releases/v<VERSION>/ for zorin (the layout that predates flavours), releases/v<VERSION>/<flavour>/ for the others.
# This is the one step that cannot be taken back: files on the public bucket get cached and mirrored. So it:
#   - checks EVERY flavour before uploading anything: all of them present, none a rehearsal, checksums right, built from this
#     commit, and nothing in the bucket that differs,
#   - never overwrites: files already in the bucket must match this build (SHA-256 of the content, and the SHA256SUMS text), else it
#     stops; matching ones are skipped, so a publish that failed half-way can simply be retried,
#   - uploads the downloads first and each flavour's SHA256SUMS last, so a half-uploaded release never has a
#     checksum file that matches,
#   - then streams every file back through the PUBLIC hostname and compares its SHA-256, which is
#     what a downloader gets (not what the bucket says it holds),
#   - only after that creates one GitHub release for all flavours (links and checksums only: GitHub caps assets at 2 GiB).
#
# Store and credentials: see iso/r2-env.sh (RELEASE_STORE=hetzner is the default). GitHub: an authenticated `gh` (or GH_TOKEN) that can create releases.
# Release notes: docs/release-notes/v<VERSION>.md is used when it exists (write the known issues
# there before tagging), followed by the generated download tables and the commit list.
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DIR="$(cd "${1:?usage: publish-release.sh <build-dir>}" && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
TAG="v$VERSION"
GH_REPO="${GH_REPO:-dazeb/noctraos}"
read -r -a FLAVOURS <<<"${RELEASE_FLAVOURS:-zorin}"
# shellcheck source=iso/r2-env.sh
source "$HERE/r2-env.sh"
log() { printf '=== %s %s\n' "$(date +%H:%M)" "$*"; }

# Per flavour: the name part, the local release folder, the bucket folder and the published files.
part() { [ "$1" = zorin ] || printf -- '-%s' "$1"; }
rel_dir() { printf '%s/release/%s%s' "$DIR" "$TAG" "$(part "$1")"; }
prefix() { if [ "$1" = zorin ]; then printf 'releases/%s' "$TAG"; else printf 'releases/%s/%s' "$TAG" "$1"; fi; }
files() { local p; p="$(part "$1")"; printf '%s\n' "noctraos-$VERSION$p-amd64.iso" "noctraos-$VERSION$p.qcow2" "noctraos-$VERSION$p.vmdk"; }

[ "${#FLAVOURS[@]}" -gt 0 ] || { echo "RELEASE_FLAVOURS is empty" >&2; exit 1; }
for fl in "${FLAVOURS[@]}"; do
  case "$fl" in zorin|kubuntu) ;; *) echo "unknown flavour in RELEASE_FLAVOURS: $fl" >&2; exit 1 ;; esac
  REL="$(rel_dir "$fl")"
  [ -f "$REL/SHA256SUMS" ] || { echo "no built $fl release at $REL: run iso/build-release.sh first" >&2; exit 1; }
  mapfile -t FILES < <(files "$fl")
  for f in "${FILES[@]}" "noctraos-$VERSION$(part "$fl")-amd64.iso.torrent"; do [ -f "$REL/$f" ] || { echo "missing $REL/$f" >&2; exit 1; }; done
  ! grep -q '^rehearsal:' "$REL/BUILD-INFO.txt" 2>/dev/null || { echo "$REL is a rehearsal build: it cannot be published" >&2; exit 1; }
  ( cd "$REL" && sha256sum -c SHA256SUMS >/dev/null ) || { echo "SHA256SUMS does not match the files in $REL" >&2; exit 1; }
  # build-release.sh builds from the tagged commit; publishing must still be that commit.
  BUILT="$(sed -n 's/^commit: *//p' "$REL/BUILD-INFO.txt")"
  [ -z "$BUILT" ] || [ "$BUILT" = "$(git -C "$ROOT" rev-parse HEAD)" ] || { echo "the $fl release was built from ${BUILT:0:7}, this checkout is $(git -C "$ROOT" rev-parse --short HEAD)" >&2; exit 1; }
done

store_env
# Resume, never overwrite: what is already there must be exactly ours, and only what is missing is uploaded.
# Anything that differs (another build of this version) stops the publish. The streamed-back SHA-256 check
# below is what finally proves every file; the size, hash and SHA256SUMS comparisons here stop a mixed release before
# anything more is uploaded.
declare -A TODO=()
for fl in "${FLAVOURS[@]}"; do
  REL="$(rel_dir "$fl")"; PREFIX="$(prefix "$fl")"
  mapfile -t FILES < <(files "$fl")
  # A listing that FAILS must stop here: an empty answer from a broken connection would look like "nothing uploaded".
  # (A prefix that does not exist yet lists as empty with exit 0.)
  REMOTE="$(rclone lsf --format 'ps' --separator '|' "$STORE_REMOTE:$STORE_BUCKET/$PREFIX/")" \
    || { echo "could not list $STORE_REMOTE:$STORE_BUCKET/$PREFIX/ (credentials or network): not publishing blind" >&2; exit 1; }
  todo=""
  for f in "${FILES[@]}" SHA256SUMS; do
    have="$(awk -F'|' -v n="$f" '$1 == n {print $2}' <<<"$REMOTE")"
    if [ -z "$have" ]; then todo+="$f"$'\n'; continue; fi
    if [ "$f" = SHA256SUMS ]; then
      rclone cat "$STORE_REMOTE:$STORE_BUCKET/$PREFIX/SHA256SUMS" | diff - "$REL/SHA256SUMS" >/dev/null \
        || { echo "$PREFIX/SHA256SUMS in the bucket differs from this build: not overwriting a published release" >&2; exit 1; }
    elif [ "$have" != "$(stat -c %s "$REL/$f")" ]; then
      echo "$PREFIX/$f in the bucket is $have bytes, this build's is $(stat -c %s "$REL/$f"): not overwriting a published release" >&2
      echo "Bump the version, or remove the old files by hand if you really mean to replace them." >&2
      exit 1
    else
      # Equal sizes prove little (ISOs of one layout are often the same size): compare content before trusting it,
      # and before SHA256SUMS goes next to it.
      want="$(awk -v n="$f" '$2 == n {print $1}' "$REL/SHA256SUMS")"
      got="$(rclone cat "$STORE_REMOTE:$STORE_BUCKET/$PREFIX/$f" | sha256sum | cut -d' ' -f1)"
      [ "$got" = "$want" ] || { echo "$PREFIX/$f in the bucket hashes to $got, this build's is $want: another build of $TAG is already there, not overwriting" >&2; exit 1; }
    fi
    echo "already uploaded: $PREFIX/$f"
  done
  TODO[$fl]="$todo"
done

for fl in "${FLAVOURS[@]}"; do
  REL="$(rel_dir "$fl")"; PREFIX="$(prefix "$fl")"
  mapfile -t todo < <(printf '%s' "${TODO[$fl]}")
  log "uploading $TAG $fl to the bucket (${#todo[@]} file(s) missing)"
  for f in "${todo[@]}"; do   # files come before SHA256SUMS, so a half-uploaded release never has matching checksums
    rclone copyto "$REL/$f" "$STORE_REMOTE:$STORE_BUCKET/$PREFIX/$f" --s3-no-check-bucket --progress --stats-one-line
  done
done

# A 17 GB stream through a CDN drops now and then (curl exit 92, HTTP/2 stream error). Piping straight into
# sha256sum cannot resume, so download into a file with Range resumption, then hash it; a drop only costs the rest.
VERIFY_TMP="$(mktemp "$DIR/verify.XXXXXX")"
trap 'rm -f "$VERIFY_TMP"' EXIT
for fl in "${FLAVOURS[@]}"; do
  REL="$(rel_dir "$fl")"; BASE="$STORE_PUBLIC_BASE/$(prefix "$fl")"
  log "verifying $fl through $BASE (what a downloader gets)"
  while read -r want name; do
    size="$(stat -c %s "$REL/$name")"
    : > "$VERIFY_TMP"
    for _try in 1 2 3 4 5 6 7 8 9 10; do
      [ "$(stat -c %s "$VERIFY_TMP")" = "$size" ] && break
      curl -sSfL -C - --connect-timeout 20 -o "$VERIFY_TMP" "$BASE/$name" || sleep "${VERIFY_RETRY_DELAY:-5}"
    done
    have="$(sha256sum "$VERIFY_TMP" | cut -d' ' -f1)"
    [ "$have" = "$want" ] || { echo "FAIL: $name from $BASE hashes to $have, expected $want" >&2; exit 1; }
    echo "OK  $name"
  done < <(sed 's/  */ /' "$REL/SHA256SUMS")
  curl -sSf "$BASE/SHA256SUMS" | diff - "$REL/SHA256SUMS" >/dev/null || { echo "FAIL: the public $fl SHA256SUMS differs" >&2; exit 1; }
done

log "creating the GitHub release $TAG"
if gh release view "$TAG" --repo "$GH_REPO" >/dev/null 2>&1; then
  echo "GitHub release $TAG already exists; leaving it as it is"
else
  NOTES="$(mktemp)"
  {
    [ ! -f "$ROOT/docs/release-notes/$TAG.md" ] || { cat "$ROOT/docs/release-notes/$TAG.md"; echo; }
    echo "## Downloads"; echo
    echo "Files are hosted on ${STORE_PUBLIC_BASE#https://} (GitHub caps release assets at 2 GiB; the ISO is larger)."
    for fl in "${FLAVOURS[@]}"; do
      REL="$(rel_dir "$fl")"; BASE="$STORE_PUBLIC_BASE/$(prefix "$fl")"
      echo
      case "$fl" in
        zorin)   echo "### NoctraOS (GNOME, Zorin OS 18.1 base)" ;;
        kubuntu) echo "### NoctraOS KDE Plasma preview (Kubuntu 26.04.1 base)" ;;
      esac
      echo
      mapfile -t FILES < <(files "$fl")
      for f in "${FILES[@]}" SHA256SUMS; do echo "- [$f]($BASE/$f)"; done
      t="noctraos-$VERSION$(part "$fl")-amd64.iso.torrent"
      echo "- [$t](https://raw.githubusercontent.com/$GH_REPO/main/$t)"
      echo; echo '```'; cat "$REL/SHA256SUMS"; echo '```'
    done
    echo
    echo "The VM disks sign in automatically as \`noctraos\` (password \`noctraos\`) with passwordless sudo: trial use only."
    prev="$(git -C "$ROOT" tag --list 'v[0-9]*' --sort=-v:refname | grep -vx "$TAG" | head -1 || true)"
    if [ -n "$prev" ]; then
      echo; echo "## Changes since $prev"; echo
      git -C "$ROOT" log -n 60 --no-merges --format='- %s (%h)' "$prev..$(git -C "$ROOT" rev-parse HEAD)" 2>/dev/null || true
    fi
  } > "$NOTES"
  # --target makes GitHub create the tag at this commit if it does not have it yet
  gh release create "$TAG" --repo "$GH_REPO" --target "$(git -C "$ROOT" rev-parse HEAD)" --title "NoctraOS $VERSION" --notes-file "$NOTES"
  rm -f "$NOTES"
fi
log "published: $STORE_PUBLIC_BASE/releases/$TAG/"
