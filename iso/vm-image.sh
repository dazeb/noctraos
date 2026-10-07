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
  local dir="$1" iso="$2" branch="$3" sha="$4" label="$5" got sysprep_out
  case "$VM_DIR" in /run/media/*|/mnt/c/*|*/ntfs*) echo "VM_DIR must be on ext4, not NTFS" >&2; return 1 ;; esac

  log "unattended install into a fresh VM ($VM_DIR)"
  "$VM" stop >/dev/null 2>&1 || true
  rm -f "$VM_DIR/disk.qcow2" "$VM_DIR/vars.fd"
  "$VM" start "$iso"
  wait_for 40 "the installed system to accept ssh" vm_ssh true

  log "waiting for first-boot provisioning (up to 90 min)"
  wait_for 90 "provisioning to finish" vm_ssh 'test -f ~/.local/share/noctraos/.provisioned'

  # Provisioning upgrades packages, and doctor flags a pending reboot. Reboot the VM (which also proves the
  # provisioned system boots again) until the flag is gone, before judging it.
  if vm_ssh 'test -f /var/run/reboot-required'; then
    log "an update needs a reboot: rebooting the VM"
    vm_ssh 'sudo systemctl reboot' >/dev/null 2>&1 || true
    sleep 45   # ssh can still answer while the old system shuts down
    wait_for 15 "ssh after the reboot" vm_ssh true
    wait_for 5 "the reboot flag to clear" vm_ssh '! test -f /var/run/reboot-required'
    wait_for 10 "the desktop session after the reboot" vm_ssh 'loginctl list-sessions --no-legend | grep noctraos >/dev/null'
  fi

  log "checking the provisioned system"
  got="$(vm_ssh 'git -C ~/.local/share/noctraos rev-parse HEAD 2>/dev/null || true' | tr -d '[:space:]')"
  # The VM's first boot fetched $branch from GitHub. If that is not the commit the rest of the release (ISO,
  # BUILD-INFO, tag) is about, the disk holds other code: stop, and build again once the branch is quiet.
  if [ -n "$got" ] && [ "$got" != "$sha" ]; then
    echo "FAIL: the VM provisioned ${got:0:7} but this build is ${sha:0:7} ($branch moved during the build?); no image written" >&2
    return 1
  fi
  [ -n "$got" ] || echo "WARNING: could not read the provisioned commit from the VM (no git clone there), so it is not verified" >&2
  # `noc doctor` always exits 0 and flags problems with "!!", so the log is what gets checked
  vm_ssh 'noc doctor' | tee "$dir/$label-doctor.log"
  if grep -q '!!' "$dir/$label-doctor.log"; then
    echo "FAIL: noc doctor reported problems (see $dir/$label-doctor.log); no image written" >&2; return 1
  fi

  log "sysprep"
  "$VM" scp "$HERE/vm-sysprep.sh"
  # The disconnect at the end can make ssh exit nonzero, so the exit code proves nothing: sysprep prints its
  # READY line only after its own hard checks (no leftover identity) have all passed. Require that line.
  sysprep_out="$(vm_ssh 'sudo NOCTRAOS_SYSPREP_YES=1 bash /tmp/vm-sysprep.sh noctraos' 2>&1 || true)"
  printf '%s\n' "$sysprep_out"
  grep -q '^\[sysprep\] READY' <<<"$sysprep_out" || { echo "FAIL: sysprep did not finish cleanly; no image written" >&2; return 1; }
  # sysprep ends ssh for good (no host keys), so the clean shutdown is the ACPI power button, not ssh
  vm_ssh 'sudo poweroff' >/dev/null 2>&1 || "$VM" powerdown >/dev/null 2>&1 || true
  sleep 20
  "$VM" status | grep -q '^running' && "$VM" powerdown >/dev/null 2>&1 || true
  wait_for 3 "the VM to power off" bash -c "! \"$VM\" status | grep -q '^running'"
}
