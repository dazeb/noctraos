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
# Runs FIRST in install.sh, before the preflight, so a VM whose setup later stops (a disk under 25 GB, no network, a closed terminal)
# still tells the host its address. ISO builds also bake qemu-guest-agent into the image (iso/bake-guest-tools.sh), so the
# KVM/Proxmox agent is there from the first boot, before anyone logs in; this module covers every other hypervisor and older images.
#
# Optional and reversible:
#   NOCTRAOS_VM_GUEST=skip     do nothing this time
#   NOCTRAOS_VM_GUEST=remove   uninstall this hypervisor's packages (apt remove, no purge) and remember the choice
#   ~/.config/noctraos/no-vm-guest   the remembered choice: while it exists, no run (first boot, update, Health > Fix) installs the tools
#                                    and `noc doctor` shows no warning. rm it to turn them back on.
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

NO_VM_GUEST="$TARGET_HOME/.config/noctraos/no-vm-guest"
# The channel the host opens for the QEMU guest agent. Without it the agent cannot start, whatever is installed.
QGA_CHANNEL="${NOC_QGA_CHANNEL:-/dev/virtio-ports/org.qemu.guest_agent.0}"

pkg_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; }

main() {
  local mode="${NOCTRAOS_VM_GUEST:-auto}" virt="" pkg
  if [ "$mode" = skip ]; then log "VM guest tools: skipped (NOCTRAOS_VM_GUEST=skip)."; return 0; fi
  if [ "$mode" != remove ] && [ "$mode" != all ] && [ -e "$NO_VM_GUEST" ]; then
    log "VM guest tools: turned off by you. To turn them back on: rm $NO_VM_GUEST, then run this module again."
    return 0
  fi
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

  if [ "$mode" = remove ]; then remove_tools "${want[@]}"; return 0; fi

  log "Virtual machine ($virt): guest tools ${want[*]}"
  # This module runs before module 01 refreshes the package index, so on a fresh install the lists can be empty: look once.
  for pkg in "${want[@]}"; do
    if ! pkg_installed "$pkg" && ! apt-cache show "$pkg" >/dev/null 2>&1; then
      sudo apt-get update -y || warn "apt-get update failed — the guest tools may not be found"
      break
    fi
  done
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
    if [ ! -e "$QGA_CHANNEL" ]; then
      warn "This VM has no QEMU guest agent channel, so the host still cannot see its address."
      warn "Proxmox: VM > Options > QEMU Guest Agent > Enabled, then shut the VM down and start it again (a restart is not enough)."
    fi
  fi
  log "VM guest tools done."
}

# remove_tools <package...>: the way back. Removes what is installed (never purges), then remembers the choice.
remove_tools() {
  local pkg
  local -a installed=()
  for pkg in "$@"; do pkg_installed "$pkg" && installed+=("$pkg"); done
  if [ "${#installed[@]}" -gt 0 ]; then
    log "Removing VM guest tools: ${installed[*]}"
    sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y "${installed[@]}" || { warn "Could not remove: ${installed[*]}"; return 0; }
  else
    log "VM guest tools: nothing installed to remove."
  fi
  as_user mkdir -p "$(dirname "$NO_VM_GUEST")" && as_user touch "$NO_VM_GUEST" \
    || warn "Could not remember the choice; the tools may come back on the next run. Create $NO_VM_GUEST by hand."
  log "VM guest tools removed and switched off. Turn them back on: rm $NO_VM_GUEST, then bash ~/.local/share/noctraos/install.sh --only 01b_vm_guest.sh"
}

# Sourced by tests: define functions only.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
