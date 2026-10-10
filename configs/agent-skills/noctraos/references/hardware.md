# Hardware: disk, GPU, VM guests

GPU detail is in [local-ai](local-ai.md). This page covers disk growth and virtual machines.

## Bigger disk (`noc disk`, `bin/noc-disk`)

A VM disk enlarged after install (Proxmox `qm resize`) leaves the new space outside the system partition; the first-boot preflight once died with "Only 18GiB free" on a 64 GB disk. **A bigger disk is noticed, never grown on its own.**

- `noc disk status [--json]` reads the layout from sysfs (no root). `noc-disk notify` raises one desktop notice per new amount (autostart `noctraos-disk-notice.desktop`).
- `sudo noc disk grow [--dry-run]` (Hardware page "Use all the disk space"; `noc-privileged disk-grow`, no arguments). Supports only the plain installer layout: root on the **last** partition, ext4/xfs/btrfs. LVM, encryption and a partition behind root are reported and left alone.
- Steps: `apt-get install fdisk` first (a default install has no `sfdisk`; it pins 11 util-linux libraries to the same version; `status` reports `needs_fdisk`), then `sfdisk --no-reread --relocate gpt-bak-std`, `sfdisk --no-reread -N <n>` with `, +`, `partx -u`, then the online filesystem grow (`resize2fs`/`xfs_growfs`/btrfs). `--no-reread` is required (else sfdisk refuses a mounted disk); its "re-reading the partition table failed" is noise on success. `parted` was rejected. If the kernel keeps the old size, `grow` exits 10, leaves the filesystem alone, and the next run finishes it.
- Consent is always explicit: the panel dialog, or a Y/n in the preflight terminal (the panel is not installed yet when preflight fails). The Health page deliberately has **no** one-click fix for it.

## VM guest tools (`install/01b_vm_guest.sh`)

A VM install needs its hypervisor's guest tools. The module picks them from `systemd-detect-virt --vm`: qemu-guest-agent + spice-vdagent (KVM/Proxmox), open-vm-tools (VMware), VirtualBox guest utils, the Hyper-V daemons; Parallels has no package (it only warns). A no-op on bare metal; never fatal.

- It is **first** in `install.sh`, before the preflight, so a failed disk/network check cannot end the run before it. The ISO bakes `qemu-guest-agent` in (`iso/bake-guest-tools.sh`, best effort) so a Proxmox VM answers before anyone logs in.
- Proxmox VMs must have the agent option on (`--agent enabled=1`; `proxmox-install.sh` does this) or the host sees nothing. Installed but no `/dev/virtio-ports/org.qemu.guest_agent.0` means that VM option is off: the module and `noc doctor` say how to set it.
- Exported disks (`iso/vm-sysprep.sh`) get `NOCTRAOS_VM_GUEST=all` because they boot on other hosts.
- Optional and reversible: `NOCTRAOS_VM_GUEST=skip|remove`; `~/.config/noctraos/no-vm-guest` keeps a removal (doctor stays quiet).
- `noc doctor` has a `vm-guest` row inside a VM, fixable from the panel via `noc-privileged module 01b_vm_guest.sh` or `noc repair vm-guest`. The package map lives twice (module and `vm_guest_primary` in `bin/noc`); `tests/test_vm_guest.py` keeps them in step. Only the KVM path has been exercised; VMware, VirtualBox and Hyper-V are untested.

## Hardware facts

The local dev workstation has an RTX 3080 Ti (it drives the desktop, so it cannot be passed through). A real AMD GPU test VM (RX 580, Vulkan) exists on TrueNAS; see [development](development.md).
