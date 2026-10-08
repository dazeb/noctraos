#!/usr/bin/env bash
# build-release.sh — build every download of a release from the tagged commit, test it, and stop.
# Publishing is a separate step (iso/publish-release.sh), so a build can be tried without going public.
#
#   iso/build-release.sh <build-dir>
#
# <build-dir> is the iso/build-local.sh directory (it must hold in/Zorin-OS-18.1-Core-64-bit.iso).
# Result: <build-dir>/release/v<VERSION>/ with
#   noctraos-<v>-amd64.iso  noctraos-<v>.qcow2  noctraos-<v>.vmdk  noctraos-<v>-amd64.iso.torrent
#   SHA256SUMS  BUILD-INFO.txt  doctor.log
# Takes 45 to 90 minutes, nearly all of it first-boot provisioning inside the VM.
#
# What it refuses (each is a way to ship the wrong thing):
#   - a VERSION that does not match the tag (CI_COMMIT_TAG, or v$VERSION when run by hand),
#   - a commit that is not the head of GitHub `main`: the ISO build clones `main` from GitHub, and
#     its first boot fetches `main`, so anything else would build a different tree than the tag,
#   - a release ISO that carries a seed or an unattended boot entry (build-local.sh checks that),
#   - a VM whose `noc doctor` reports problems, and an exported disk that does not boot.
# Run it from a checkout of the tag. Needs docker, qemu/KVM, OVMF, python3-venv and ~120 GB free.
#
# Rehearsal: RELEASE_REHEARSAL=1 REHEARSAL_BRANCH=<branch on GitHub> builds and tests everything from that branch
# without the tag and `main` checks, into release/v<VERSION>-rehearsal/. publish-release.sh cannot
# publish a rehearsal. Use it to try changes to the pipeline itself.
#
# Environment: REPO_URL (https://github.com/dazeb/noctraos.git), VM_DIR (noctraos-release-vm on the fastest
# disk with room, see iso/disks.sh; a Linux filesystem only), VM_SSH_PORT (2225), VM_RAM, VM_CPUS, NOCTRAOS_KEEP_VM=1 to keep the VM disk afterwards.
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DIR="$(cd "${1:?usage: build-release.sh <build-dir>}" && pwd)"
REPO_URL="${REPO_URL:-https://github.com/dazeb/noctraos.git}"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
TAG="${CI_COMMIT_TAG:-v$VERSION}"
# shellcheck source=iso/disks.sh
source "$HERE/disks.sh"
export VM_DIR="${VM_DIR:-$(fast_dir noctraos-release-vm)}" VM_SSH_PORT="${VM_SSH_PORT:-2225}"
export VM_DISK_SIZE="${VM_DISK_SIZE:-64G}"
VM="$HERE/local-vm.sh"
# shellcheck source=iso/vm-image.sh
source "$HERE/vm-image.sh"
REHEARSAL="${RELEASE_REHEARSAL:-0}"
BRANCH=main
OUT="$DIR/release/v$VERSION"
if [ "$REHEARSAL" = 1 ]; then
  BRANCH="${REHEARSAL_BRANCH:?RELEASE_REHEARSAL=1 needs REHEARSAL_BRANCH (a branch on GitHub)}"
  OUT="$OUT-rehearsal"
fi

[ "$REHEARSAL" = 1 ] || [ "$TAG" = "v$VERSION" ] || { echo "tag $TAG does not match VERSION $VERSION: fix VERSION (and bin/noc, bin/noc-gpu) and tag again" >&2; exit 1; }
for f in bin/noc bin/noc-gpu; do
  grep -q "^VERSION=\"$VERSION\"" "$ROOT/$f" || { echo "$f does not match VERSION $VERSION" >&2; exit 1; }
done
[ -f "$DIR/in/Zorin-OS-18.1-Core-64-bit.iso" ] || { echo "missing $DIR/in/Zorin-OS-18.1-Core-64-bit.iso (the base ISO)" >&2; exit 1; }
# Fail in seconds, not after a 20 minute ISO build: the VM disk and the build scratch need real room on a Linux filesystem.
require_linux_fs "$VM_DIR" && require_linux_fs "$DIR" || exit 1
require_free_gb "$VM_DIR" "${RELEASE_MIN_FREE_GB:-100}" && require_free_gb "$DIR" "${RELEASE_MIN_BUILD_FREE_GB:-60}" || exit 1

SHA="$(git -C "$ROOT" rev-parse HEAD)"
MAIN="$(git ls-remote "$REPO_URL" "refs/heads/$BRANCH" | cut -c1-40)"
[ -n "$MAIN" ] || { echo "could not read $BRANCH from $REPO_URL" >&2; exit 1; }
[ "$REHEARSAL" = 1 ] && SHA="$MAIN"   # a rehearsal builds what GitHub has on the branch
[ "$SHA" = "$MAIN" ] || { echo "tag $TAG is ${SHA:0:7} but GitHub main is ${MAIN:0:7}. The build clones main: push/merge so main is the commit you tagged, then tag again." >&2; exit 1; }
log "building ${TAG}$([ "$REHEARSAL" = 1 ] && echo " (REHEARSAL from $BRANCH)") @ ${SHA:0:7} into $OUT"

rm -rf "$OUT"; mkdir -p "$OUT"
"$VM" stop >/dev/null 2>&1 || true

log "1/6 release ISO and appliance ISO"
rm -f "$DIR"/out/noctraos-*-amd64.iso "$DIR"/out/noctraos-*-appliance-build.iso
REPO_URL="$REPO_URL" NOCTRAOS_BRANCH="$BRANCH" "$HERE/build-local.sh" "$DIR" both
ISO="$DIR/out/noctraos-$VERSION-amd64.iso"
APPLIANCE="$DIR/out/noctraos-$VERSION-appliance-build.iso"
[ -f "$ISO" ] && [ -f "$APPLIANCE" ] || { echo "build-local.sh did not write the expected ISOs for $VERSION" >&2; exit 1; }

log "2/6 provisioned VM disk"
vm_image_build "$DIR" "$APPLIANCE" "$BRANCH" "$SHA" release
cp "$DIR/release-doctor.log" "$OUT/doctor.log"

log "3/6 exporting the disks"
# Both conversions compress on one core each (about 15 minutes apiece): run them side by side.
qemu-img convert -O qcow2 -c "$VM_DIR/disk.qcow2" "$OUT/noctraos-$VERSION.qcow2" & QCOW_PID=$!
qemu-img convert -O vmdk -o subformat=streamOptimized "$VM_DIR/disk.qcow2" "$OUT/noctraos-$VERSION.vmdk" & VMDK_PID=$!
# Wait for BOTH before judging: bailing out while one is still writing would leave it running into $OUT.
EXPORT_FAILED=0
wait "$QCOW_PID" || EXPORT_FAILED=1
wait "$VMDK_PID" || EXPORT_FAILED=1
[ "$EXPORT_FAILED" = 0 ] || { echo "exporting the disks failed" >&2; exit 1; }
[ "${NOCTRAOS_KEEP_VM:-0}" = 1 ] || rm -rf "$VM_DIR"
cp --reflink=auto "$ISO" "$OUT/noctraos-$VERSION-amd64.iso"

log "4/6 torrent"
VENV="$DIR/torf-venv"
[ -x "$VENV/bin/python" ] || { python3 -m venv "$VENV" && "$VENV/bin/pip" install -q torf; }
"$VENV/bin/python" "$ROOT/scripts/make-torrent.py" "$OUT/noctraos-$VERSION-amd64.iso" "$VERSION" "$OUT/noctraos-$VERSION-amd64.iso.torrent"

log "5/6 checksums"
( cd "$OUT" && sha256sum "noctraos-$VERSION-amd64.iso" "noctraos-$VERSION.qcow2" "noctraos-$VERSION.vmdk" > SHA256SUMS && cat SHA256SUMS )
{
  if [ "$REHEARSAL" = 1 ]; then echo "rehearsal: yes (branch $BRANCH): NOT a release, never publish"; else echo "release: $TAG"; fi
  echo "commit:  $SHA"
  echo "built:   $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "login:   noctraos / noctraos (the VM disks: autologin, passwordless sudo, trial use only)"
} > "$OUT/BUILD-INFO.txt"

log "6/6 boot test of the exported disk"
"$HERE/boot-test-image.sh" "$OUT/noctraos-$VERSION.qcow2"

rm -f "$APPLIANCE"   # carries autologin and a throwaway password: it must never be left lying around as a release file
log "done: $OUT"; ls -lh "$OUT"
