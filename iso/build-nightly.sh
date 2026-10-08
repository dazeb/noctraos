#!/usr/bin/env bash
# build-nightly.sh — build the nightly download: a READY-MADE, already provisioned VM disk built
# from the `nightly` branch. Nobody waits for (or loses to) the 25 to 40 minute first-boot
# provisioning: it runs here, and the image is only produced if it finished and `noc doctor` passed.
#
#   iso/build-nightly.sh <build-dir> [--upload]
#
# <build-dir> is the iso/build-local.sh directory (it must hold in/Zorin-OS-18.1-Core-64-bit.iso).
# Result: <build-dir>/out/nightly/{noctraos-nightly.qcow2, SHA256SUMS, BUILD-INFO.txt}.
#
# Steps: build an appliance ISO from `nightly` (the branch is baked in, so first boot fetches
# `nightly`, not `main`) -> install it unattended in a throwaway local KVM VM -> wait for
# provisioning -> check the provisioned branch and `noc doctor` -> sysprep -> export qcow2.
# About 45 to 60 minutes, almost all of it provisioning. Run it from `nightly` pushed to GitHub.
#
# --upload copies the three files to files.dazeb.dev/nightly/ (public, stable names, overwritten
# each build). Nothing is uploaded without the flag. The image is a trial appliance: autologin,
# user noctraos / password noctraos, passwordless sudo. It is for testing, never for production.
#
# Environment: VM_DIR (default: noctraos-nightly-vm on the fastest disk, see iso/disks.sh; a Linux filesystem, NOT NTFS), VM_SSH_PORT (2223,
# so it can run beside the 2222 test VM), VM_RAM, VM_CPUS, NIGHTLY_BRANCH (nightly).
set -Eeuo pipefail

DIR="${1:?usage: build-nightly.sh <build-dir> [--upload]}"
UPLOAD=0; [ "${2:-}" = "--upload" ] && UPLOAD=1
BRANCH="${NIGHTLY_BRANCH:-nightly}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=iso/disks.sh
source "$HERE/disks.sh"
export VM_DIR="${VM_DIR:-$(fast_dir noctraos-nightly-vm)}" VM_SSH_PORT="${VM_SSH_PORT:-2223}"
export VM_DISK_SIZE="${VM_DISK_SIZE:-64G}"
VM="$HERE/local-vm.sh"
OUT="$DIR/out/nightly"
# shellcheck source=iso/vm-image.sh
source "$HERE/vm-image.sh"
# shellcheck source=iso/r2-env.sh
source "$HERE/r2-env.sh"

SHA="$(git ls-remote origin "refs/heads/$BRANCH" | cut -c1-40)"
[ -n "$SHA" ] || { echo "origin has no '$BRANCH' branch: push it first (the ISO build clones from GitHub)" >&2; exit 1; }
log "building $BRANCH @ ${SHA:0:7}"

"$VM" stop >/dev/null 2>&1 || true
log "appliance ISO from $BRANCH"
NOCTRAOS_BRANCH="$BRANCH" "$HERE/build-local.sh" "$DIR" appliance
ISO="$(ls -t "$DIR"/out/noctraos-*-appliance-build.iso | head -1)"

vm_image_build "$DIR" "$ISO" "$BRANCH" "$SHA" nightly
mkdir -p "$OUT"
qemu-img convert -p -O qcow2 -c "$VM_DIR/disk.qcow2" "$OUT/noctraos-nightly.qcow2"
( cd "$OUT" && sha256sum noctraos-nightly.qcow2 > SHA256SUMS )
{
  echo "branch:  $BRANCH"
  echo "commit:  $SHA"
  echo "built:   $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "login:   noctraos / noctraos (autologin, passwordless sudo): a test appliance, never production"
} > "$OUT/BUILD-INFO.txt"
log "done: $OUT"; ls -lh "$OUT"

if [ "$UPLOAD" = 1 ]; then
  log "uploading to files.dazeb.dev/nightly/"
  r2_env
  # image first, checksum and info last: a half-uploaded image never has a matching SHA256SUMS
  for f in noctraos-nightly.qcow2 SHA256SUMS BUILD-INFO.txt; do
    rclone copyto "$OUT/$f" "r2:$R2_BUCKET/nightly/$f" -P
  done
  echo "public: https://files.dazeb.dev/nightly/noctraos-nightly.qcow2"
fi
