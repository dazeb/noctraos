#!/usr/bin/env bash
# boot-test-image.sh — boot an exported VM disk once and check it comes up the way a downloader sees it.
#
#   iso/boot-test-image.sh <disk.qcow2>
#
# The disk is never modified: the VM runs on a throwaway overlay. Passes when the image reaches ssh,
# autologs the user into a desktop session, and has made itself a new SSH host key (the sysprep
# removes them). Uses its own VM directory and ssh port (BOOT_TEST_VM_DIR, BOOT_TEST_SSH_PORT 2224), ext4 only.
set -Eeuo pipefail

DISK="$(readlink -f "${1:?usage: boot-test-image.sh <disk.qcow2>}")"
[ -f "$DISK" ] || { echo "no such disk: $DISK" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
# Its own variables: build-release.sh calls this with the build VM's VM_DIR/VM_SSH_PORT exported, and this
# script deletes its VM directory.
# shellcheck source=iso/disks.sh
source "$HERE/disks.sh"
export VM_DIR="${BOOT_TEST_VM_DIR:-$(fast_dir noctraos-boottest-vm)}" VM_SSH_PORT="${BOOT_TEST_SSH_PORT:-2224}"
VM="$HERE/local-vm.sh"
# shellcheck source=iso/vm-image.sh
source "$HERE/vm-image.sh"
require_linux_fs "$VM_DIR" || exit 1

cleanup() { "$VM" stop >/dev/null 2>&1 || true; rm -rf "$VM_DIR"; }
trap cleanup EXIT
"$VM" stop >/dev/null 2>&1 || true
rm -rf "$VM_DIR"; mkdir -p "$VM_DIR"
qemu-img create -q -f qcow2 -b "$DISK" -F qcow2 "$VM_DIR/disk.qcow2"

log "booting $DISK on an overlay"
"$VM" start none
wait_for 20 "the image to accept ssh" vm_ssh true
wait_for 10 "autologin to start a desktop session" vm_ssh 'loginctl list-sessions --no-legend | grep -q noctraos'
vm_ssh 'test -s /etc/ssh/ssh_host_ed25519_key.pub' || { echo "FAIL: no SSH host key was generated" >&2; exit 1; }
vm_ssh 'test -s /etc/machine-id' || { echo "FAIL: no machine id" >&2; exit 1; }
log "boot test passed: ssh, autologin session, new host key"
