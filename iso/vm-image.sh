#!/usr/bin/env bash
# vm-image.sh — the part that nightly and release builds share: turn an appliance ISO into a
# provisioned, sysprepped VM disk. Sourced, not run.
#
#   vm_image_build <build-dir> <iso> <branch> <expected-sha> <label>
#
# Installs <iso> unattended into a throwaway local KVM VM (iso/local-vm.sh), waits for first-boot
# provisioning, refuses the image unless `noc doctor` is clean, runs the sysprep and powers the VM
# off. The finished disk is $VM_DIR/disk.qcow2: the caller converts and publishes it. The doctor
# output is kept in <build-dir>/<label>-doctor.log.
#
# Needs the caller to have set HERE (the iso/ directory), VM (local-vm.sh) and exported VM_DIR,
# VM_SSH_PORT and VM_DISK_SIZE. VM_DIR must be on ext4, never NTFS.

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

vm_image_build() {
  local dir="$1" iso="$2" branch="$3" sha="$4" label="$5" got
  case "$VM_DIR" in /run/media/*|/mnt/c/*|*/ntfs*) echo "VM_DIR must be on ext4, not NTFS" >&2; return 1 ;; esac

  log "unattended install into a fresh VM ($VM_DIR)"
  "$VM" stop >/dev/null 2>&1 || true
  rm -f "$VM_DIR/disk.qcow2" "$VM_DIR/vars.fd"
  "$VM" start "$iso"
  wait_for 40 "the installed system to accept ssh" vm_ssh true

  log "waiting for first-boot provisioning (up to 90 min)"
  wait_for 90 "provisioning to finish" vm_ssh 'test -f ~/.local/share/noctraos/.provisioned'

  log "checking the provisioned system"
  got="$(vm_ssh 'git -C ~/.local/share/noctraos rev-parse HEAD 2>/dev/null || true' | tr -d '[:space:]')"
  if [ -n "$got" ] && [ "$got" != "$sha" ]; then
    echo "WARNING: provisioned ${got:0:7} but $branch is now ${sha:0:7} (pushed during the build?)" >&2
  fi
  # `noc doctor` always exits 0 and flags problems with "!!", so the log is what gets checked
  vm_ssh 'noc doctor' | tee "$dir/$label-doctor.log"
  if grep -q '!!' "$dir/$label-doctor.log"; then
    echo "FAIL: noc doctor reported problems (see $dir/$label-doctor.log); no image written" >&2; return 1
  fi

  log "sysprep"
  "$VM" scp "$HERE/vm-sysprep.sh"
  vm_ssh 'sudo NOCTRAOS_SYSPREP_YES=1 bash /tmp/vm-sysprep.sh noctraos' || true   # the disconnect ends the session
  vm_ssh 'sudo poweroff' >/dev/null 2>&1 || true
  wait_for 3 "the VM to power off" bash -c "! \"$VM\" status | grep -q '^running'"
}
