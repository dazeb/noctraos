#!/usr/bin/env bash
# Module 01b: VM guest tools. Inside a virtual machine NoctraOS needs the hypervisor's guest agent, or the host cannot
# shut the VM down cleanly, read its IP address, share the clipboard or follow a window resize. Bare metal: nothing to do.
#
#   kvm / qemu   qemu-guest-agent (Proxmox, libvirt, plain QEMU) and spice-vdagent (clipboard, resize on SPICE displays)
#   vmware       open-vm-tools and open-vm-tools-desktop
#   oracle       virtualbox-guest-utils and virtualbox-guest-x11 (VirtualBox)
#   microsoft    the Hyper-V daemons (linux-tools-virtual, linux-cloud-tools-virtual)
#   parallels    no Linux package exists: Parallels Tools come from the Parallels Desktop menu
#
# NOCTRAOS_VM_GUEST=all installs every set above whatever the host is. That is for a disk image that will boot on a hypervisor
# other than the one it was built on (iso/vm-sysprep.sh sets it); each package is inert on a host it does not belong to.
# Re-runnable from the Control Panel (Health > Fix, through noc-privileged) and by hand:
#   bash ~/.local/share/noctraos/install.sh --only 01b_vm_guest.sh
# bin/noc doctor checks the first package of each set (vm_guest_primary there); tests/test_vm_guest.py keeps the two in step.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

# vm_guest_packages <hypervisor>: what to install for what systemd-detect-virt --vm calls it.
vm_guest_packages() {
  case "$1" in
    kvm|qemu|bochs) echo "qemu-guest-agent spice-vdagent" ;;
    vmware)         echo "open-vm-tools open-vm-tools-desktop" ;;
    oracle)         echo "virtualbox-guest-utils virtualbox-guest-x11" ;;
    microsoft)      echo "linux-tools-virtual linux-cloud-tools-virtual" ;;
    all)            echo "$(vm_guest_packages kvm) $(vm_guest_packages vmware) $(vm_guest_packages oracle) $(vm_guest_packages microsoft)" ;;
    *)              echo "" ;;
  esac
}

pkg_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; }

main() {
  local mode="${NOCTRAOS_VM_GUEST:-auto}" virt="" pkg
  if [ "$mode" = all ]; then
    virt=all
  else
    virt="$(systemd-detect-virt --vm 2>/dev/null || true)"
  fi
  case "$virt" in
    ''|none) log "Bare metal: no VM guest tools needed."; return 0 ;;
    parallels) warn "Parallels VM: install Parallels Tools from the Parallels Desktop menu (Actions > Install Parallels Tools)."; return 0 ;;
  esac

  local -a want=()
  for pkg in $(vm_guest_packages "$virt"); do want+=("$pkg"); done
  if [ "${#want[@]}" -eq 0 ]; then
    log "Virtual machine ($virt): no guest tools known for this hypervisor."
    return 0
  fi

  log "Virtual machine ($virt): guest tools ${want[*]}"
  for pkg in "${want[@]}"; do
    if pkg_installed "$pkg"; then
      log "OK: $pkg already installed"
    elif apt-cache show "$pkg" >/dev/null 2>&1; then
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg" || warn "VM guest package failed to install: $pkg"
    else
      warn "VM guest package not available in this release (skipped): $pkg"
    fi
  done

  # The agent normally starts when udev sees the host's channel, which a package installed into a running VM only gets at
  # the next boot; start it now so the host sees the VM straight away. Harmless if it is not there or already running.
  if [ "$mode" != all ] && pkg_installed qemu-guest-agent; then
    sudo systemctl start qemu-guest-agent >/dev/null 2>&1 || true
  fi
  log "VM guest tools done."
}

# Sourced by tests: define functions only.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
