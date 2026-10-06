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
# Environment: VM_DIR (default /mnt/nvme1/noctraos-nightly-vm; ext4, NOT NTFS), VM_SSH_PORT (2223,
# so it can run beside the 2222 test VM), VM_RAM, VM_CPUS, NIGHTLY_BRANCH (nightly).
set -Eeuo pipefail

DIR="${1:?usage: build-nightly.sh <build-dir> [--upload]}"
UPLOAD=0; [ "${2:-}" = "--upload" ] && UPLOAD=1
BRANCH="${NIGHTLY_BRANCH:-nightly}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export VM_DIR="${VM_DIR:-/mnt/nvme1/noctraos-nightly-vm}" VM_SSH_PORT="${VM_SSH_PORT:-2223}"
export VM_DISK_SIZE="${VM_DISK_SIZE:-64G}"
VM="$HERE/local-vm.sh"
OUT="$DIR/out/nightly"
log() { printf '=== %s %s\n' "$(date +%H:%M)" "$*"; }
vm_ssh() { "$VM" ssh "$@"; }
wait_for() {  # wait_for <minutes> <description> <command...>
  local mins="$1" what="$2"; shift 2
  local end=$(( $(date +%s) + mins * 60 ))
  until "$@" >/dev/null 2>&1; do
    [ "$(date +%s)" -lt "$end" ] || { echo "timed out after ${mins} min waiting for: $what" >&2; return 1; }
    sleep 20
  done
}

case "$VM_DIR" in /run/media/*|/mnt/c/*|*/ntfs*) echo "VM_DIR must be on ext4, not NTFS" >&2; exit 1 ;; esac
SHA="$(git ls-remote origin "refs/heads/$BRANCH" | cut -c1-40)"
[ -n "$SHA" ] || { echo "origin has no '$BRANCH' branch: push it first (the ISO build clones from GitHub)" >&2; exit 1; }
log "building $BRANCH @ ${SHA:0:7}"

"$VM" stop >/dev/null 2>&1 || true
log "1/5 appliance ISO from $BRANCH"
NOCTRAOS_BRANCH="$BRANCH" "$HERE/build-local.sh" "$DIR" appliance
ISO="$(ls -t "$DIR"/out/noctraos-*-appliance-build.iso | head -1)"

log "2/5 unattended install into a fresh VM ($VM_DIR)"
rm -f "$VM_DIR/disk.qcow2" "$VM_DIR/vars.fd"
"$VM" start "$ISO"
wait_for 40 "the installed system to accept ssh" vm_ssh true

log "3/5 waiting for first-boot provisioning (up to 90 min)"
wait_for 90 "provisioning to finish" vm_ssh 'test -f ~/.local/share/noctraos/.provisioned'

log "4/5 checking the provisioned system"
got="$(vm_ssh 'git -C ~/.local/share/noctraos rev-parse HEAD 2>/dev/null || true' | tr -d '[:space:]')"
if [ -n "$got" ] && [ "$got" != "$SHA" ]; then
  echo "WARNING: provisioned ${got:0:7} but $BRANCH is now ${SHA:0:7} (pushed during the build?)" >&2
fi
# `noc doctor` always exits 0 and flags problems with "!!", so the log is what gets checked
vm_ssh 'noc doctor' | tee "$DIR/nightly-doctor.log"
if grep -q '!!' "$DIR/nightly-doctor.log"; then
  echo "FAIL: noc doctor reported problems (see $DIR/nightly-doctor.log); no image written" >&2; exit 1
fi

log "5/5 sysprep and export"
"$VM" scp "$HERE/vm-sysprep.sh"
vm_ssh 'sudo NOCTRAOS_SYSPREP_YES=1 bash /tmp/vm-sysprep.sh noctraos' || true   # the disconnect ends the session
vm_ssh 'sudo poweroff' >/dev/null 2>&1 || true
wait_for 3 "the VM to power off" bash -c "! \"$VM\" status | grep -q '^running'"
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
  set -a
  # shellcheck disable=SC1090
  source ~/secrets/cloudflare-r2.env
  set +a
  export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
    RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT"
  # image first, checksum and info last: a half-uploaded image never has a matching SHA256SUMS
  for f in noctraos-nightly.qcow2 SHA256SUMS BUILD-INFO.txt; do
    rclone copyto "$OUT/$f" "r2:$R2_BUCKET/nightly/$f" -P
  done
  echo "public: https://files.dazeb.dev/nightly/noctraos-nightly.qcow2"
fi
