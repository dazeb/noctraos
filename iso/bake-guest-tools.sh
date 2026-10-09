#!/usr/bin/env bash
# bake-guest-tools.sh — puts the QEMU guest agent into the image, so a KVM/Proxmox VM answers its host from the first boot.
# Sourced by build-noctraos-iso.sh.
#
#   bake_guest_tools <squashfs-root>
#
# Why: the provisioner (install/01b_vm_guest.sh) only runs after someone logs in, types the sudo password and the setup gets
# going, so a fresh VM showed no IP address in Proxmox for as long as that took, or for ever when the setup stopped early.
# qemu-guest-agent is tiny and inert off KVM (its service waits for the host's virtio channel), so it ships in every image;
# the other hypervisors' tools stay with the provisioner, because VirtualBox/VMware packages are dead weight on bare metal.
#
# Best effort: this never fails the build (no network in the builder, a mirror hiccup). The provisioner installs the agent
# anyway; a build that could not bake it says so loudly. Needs root (chroot) and the network, like the clone in step 4.

bake_guest_tools() {
  local root="$1" pkg=qemu-guest-agent resolv="$1/etc/resolv.conf" had_resolv=0
  if [ -x "$root/usr/sbin/qemu-ga" ] || [ -x "$root/usr/bin/qemu-ga" ]; then
    echo "bake_guest_tools: $pkg is already in the image"
    return 0
  fi
  # apt in the chroot needs a resolver. The image's own file may be a dangling symlink into /run: put ours in, restore after.
  if [ -e "$resolv" ] || [ -L "$resolv" ]; then had_resolv=1; mv "$resolv" "$resolv.noctraos-bak"; fi
  cp /etc/resolv.conf "$resolv" 2>/dev/null || true
  if chroot "$root" /bin/sh -c "
       export DEBIAN_FRONTEND=noninteractive
       apt-get update -y && apt-get install -y --no-install-recommends $pkg
       rc=\$?
       apt-get clean
       exit \$rc" >/dev/null 2>&1; then
    echo "bake_guest_tools: $pkg baked into the image"
  else
    echo "WARNING: bake_guest_tools could not install $pkg into the image; the provisioner will install it after first login" >&2
  fi
  rm -f "$resolv"
  [ "$had_resolv" = 1 ] && mv "$resolv.noctraos-bak" "$resolv"
  # The lists only served this install; the first-boot provisioner refreshes them (module 01) before it needs any.
  rm -rf "$root"/var/lib/apt/lists/*
  return 0
}
