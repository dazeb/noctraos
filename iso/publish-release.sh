#!/usr/bin/env bash
# publish-release.sh — put a built release on dl.noctraos.dev and create the GitHub release.
#
#   iso/publish-release.sh <build-dir>
#
# Reads <build-dir>/release/v<VERSION>/ (written by iso/build-release.sh). This is the one step that
# cannot be taken back: files on the public bucket get cached and mirrored. So it:
#   - never overwrites: files already in the bucket must match this build (SHA-256 of the content, and the SHA256SUMS text), else it
#     stops; matching ones are skipped, so a publish that failed half-way can simply be retried,
#   - uploads the three downloads first and SHA256SUMS last, so a half-uploaded release never has a
#     checksum file that matches,
#   - then streams every file back through the PUBLIC hostname and compares its SHA-256, which is
#     what a downloader gets (not what the bucket says it holds),
#   - only after that creates the GitHub release (links and checksums only: GitHub caps assets at 2 GiB).
#
# Credentials: see iso/r2-env.sh. GitHub: an authenticated `gh` (or GH_TOKEN) that can create releases.
# Release notes: docs/release-notes/v<VERSION>.md is used when it exists (write the known issues
# there before tagging), followed by the generated download table and the commit list.
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DIR="$(cd "${1:?usage: publish-release.sh <build-dir>}" && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
TAG="v$VERSION"
REL="$DIR/release/$TAG"
BASE="https://dl.noctraos.dev/releases/$TAG"
GH_REPO="${GH_REPO:-dazeb/noctraos}"
# shellcheck source=iso/r2-env.sh
source "$HERE/r2-env.sh"
log() { printf '=== %s %s\n' "$(date +%H:%M)" "$*"; }

[ -f "$REL/SHA256SUMS" ] || { echo "no built release at $REL: run iso/build-release.sh first" >&2; exit 1; }
FILES=("noctraos-$VERSION-amd64.iso" "noctraos-$VERSION.qcow2" "noctraos-$VERSION.vmdk")
for f in "${FILES[@]}" "noctraos-$VERSION-amd64.iso.torrent"; do [ -f "$REL/$f" ] || { echo "missing $REL/$f" >&2; exit 1; }; done
! grep -q '^rehearsal:' "$REL/BUILD-INFO.txt" 2>/dev/null || { echo "$REL is a rehearsal build: it cannot be published" >&2; exit 1; }
( cd "$REL" && sha256sum -c SHA256SUMS >/dev/null ) || { echo "SHA256SUMS does not match the files in $REL" >&2; exit 1; }
# build-release.sh builds from the tagged commit; publishing must still be that commit.
BUILT="$(sed -n 's/^commit: *//p' "$REL/BUILD-INFO.txt")"
[ -z "$BUILT" ] || [ "$BUILT" = "$(git -C "$ROOT" rev-parse HEAD)" ] || { echo "the release was built from ${BUILT:0:7}, this checkout is $(git -C "$ROOT" rev-parse --short HEAD)" >&2; exit 1; }

r2_env
# Resume, never overwrite: what is already there must be exactly ours, and only what is missing is uploaded.
# Anything that differs (another build of this version) stops the publish. The streamed-back SHA-256 check
# below is what finally proves every file; the size, hash and SHA256SUMS comparisons here stop a mixed release before
# anything more is uploaded.
# A listing that FAILS must stop here: an empty answer from a broken connection would look like "nothing uploaded".
# (A prefix that does not exist yet lists as empty with exit 0.)
REMOTE="$(rclone lsf --format 'ps' --separator '|' "r2:$R2_BUCKET/releases/$TAG/")" \
  || { echo "could not list r2:$R2_BUCKET/releases/$TAG/ (credentials or network): not publishing blind" >&2; exit 1; }
remote_size() { awk -F'|' -v n="$1" '$1 == n {print $2}' <<<"$REMOTE"; }
TODO=()
for f in "${FILES[@]}" SHA256SUMS; do
  have="$(remote_size "$f")"
  if [ -z "$have" ]; then TODO+=("$f"); continue; fi
  if [ "$f" = SHA256SUMS ]; then
    rclone cat "r2:$R2_BUCKET/releases/$TAG/SHA256SUMS" | diff - "$REL/SHA256SUMS" >/dev/null \
      || { echo "releases/$TAG/SHA256SUMS in the bucket differs from this build: not overwriting a published release" >&2; exit 1; }
  elif [ "$have" != "$(stat -c %s "$REL/$f")" ]; then
    echo "releases/$TAG/$f in the bucket is $have bytes, this build's is $(stat -c %s "$REL/$f"): not overwriting a published release" >&2
    echo "Bump the version, or remove the old files by hand if you really mean to replace them." >&2
    exit 1
  else
    # Equal sizes prove little (ISOs of one layout are often the same size): compare content before trusting it,
    # and before SHA256SUMS goes next to it.
    want="$(awk -v n="$f" '$2 == n {print $1}' "$REL/SHA256SUMS")"
    got="$(rclone cat "r2:$R2_BUCKET/releases/$TAG/$f" | sha256sum | cut -d' ' -f1)"
    [ "$got" = "$want" ] || { echo "releases/$TAG/$f in the bucket hashes to $got, this build's is $want: another build of $TAG is already there, not overwriting" >&2; exit 1; }
  fi
  echo "already uploaded: $f"
done

log "uploading $TAG to the bucket (${#TODO[@]} file(s) missing)"
for f in "${TODO[@]}"; do   # FILES come before SHA256SUMS, so a half-uploaded release never has matching checksums
  rclone copyto "$REL/$f" "r2:$R2_BUCKET/releases/$TAG/$f" --s3-no-check-bucket --progress --stats-one-line
done

log "verifying through $BASE (what a downloader gets)"
while read -r want name; do
  have="$(curl -sSfL --retry 3 "$BASE/$name" | sha256sum | cut -d' ' -f1)"
  [ "$have" = "$want" ] || { echo "FAIL: $name from $BASE hashes to $have, expected $want" >&2; exit 1; }
  echo "OK  $name"
done < <(sed 's/  */ /' "$REL/SHA256SUMS")
curl -sSf "$BASE/SHA256SUMS" | diff - "$REL/SHA256SUMS" >/dev/null || { echo "FAIL: the public SHA256SUMS differs" >&2; exit 1; }

log "creating the GitHub release $TAG"
if gh release view "$TAG" --repo "$GH_REPO" >/dev/null 2>&1; then
  echo "GitHub release $TAG already exists; leaving it as it is"
else
  NOTES="$(mktemp)"
  {
    [ ! -f "$ROOT/docs/release-notes/$TAG.md" ] || { cat "$ROOT/docs/release-notes/$TAG.md"; echo; }
    echo "## Downloads"; echo
    echo "Files are hosted on dl.noctraos.dev (GitHub caps release assets at 2 GiB; the ISO is larger)."; echo
    for f in "${FILES[@]}" SHA256SUMS; do echo "- [$f]($BASE/$f)"; done
    echo "- [noctraos-$VERSION-amd64.iso.torrent](https://raw.githubusercontent.com/$GH_REPO/main/noctraos-$VERSION-amd64.iso.torrent)"
    echo; echo '```'; cat "$REL/SHA256SUMS"; echo '```'; echo
    echo "The VM disks sign in automatically as \`noctraos\` (password \`noctraos\`) with passwordless sudo: trial use only."
    prev="$(git -C "$ROOT" tag --list 'v[0-9]*' --sort=-v:refname | grep -vx "$TAG" | head -1 || true)"
    if [ -n "$prev" ]; then
      echo; echo "## Changes since $prev"; echo
      git -C "$ROOT" log --no-merges --format='- %s (%h)' "$prev..$(git -C "$ROOT" rev-parse HEAD)" 2>/dev/null | head -60
    fi
  } > "$NOTES"
  # --target makes GitHub create the tag at this commit if it does not have it yet
  gh release create "$TAG" --repo "$GH_REPO" --target "$(git -C "$ROOT" rev-parse HEAD)" --title "NoctraOS $VERSION" --notes-file "$NOTES"
  rm -f "$NOTES"
fi
log "published: $BASE/"
