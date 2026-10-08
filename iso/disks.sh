#!/usr/bin/env bash
# disks.sh — where VM test disks and ISO build scratch go. Sourced by the VM and build scripts.
#
#   fast_disk            the fastest candidate disk that is a real Linux filesystem with room (default 100 GB free)
#   fast_dir <name>      <fast_disk>/<name>, the default location of a VM or build directory
#   require_linux_fs <dir>        fail unless <dir> (or its nearest existing parent) is on a Linux filesystem, not NTFS/FAT/exFAT
#   require_free_gb <dir> <GB>    fail unless that much is free on the filesystem holding <dir>
#
# Policy (the user's rule): VM disks and ISO scratch always go on the FASTEST local disk, and "fastest" is measured, not
# assumed: `iso/fastest-disk.sh` benchmarks the candidates. The list below is that measurement, best first
# (2026-10-08, this workstation: Crucial P310 2 TB 2.2 GB/s write, 16k QD1 random reads; Samsung 960 PRO 0.6-1.1 GB/s,
# 7k). Re-run the benchmark after any hardware change and reorder. NOCTRAOS_DISK_CANDIDATES overrides the list.
NOCTRAOS_DISK_CANDIDATES="${NOCTRAOS_DISK_CANDIDATES:-/run/media/dazeb/2tb /mnt/nvme1}"
NOCTRAOS_MIN_FREE_GB="${NOCTRAOS_MIN_FREE_GB:-100}"

_nearest_dir() { local d="$1"; while [ ! -d "$d" ] && [ "$d" != / ]; do d="$(dirname "$d")"; done; printf '%s' "$d"; }

# NOCTRAOS_EXTRA_FS: more filesystem type names (as `stat -f -c %T` prints them) to accept, space separated. For tests that run
# in a checkout on tmpfs and for unusual setups; the defaults are what a VM disk should live on.
linux_fs() {
  local fs
  fs="$(stat -f -c %T "$(_nearest_dir "$1")" 2>/dev/null)"
  case "$fs" in
    ext2/ext3|ext4|xfs|btrfs|zfs|f2fs|overlayfs) return 0 ;;
    *) [ -n "$fs" ] && case " ${NOCTRAOS_EXTRA_FS:-} " in *" $fs "*) return 0 ;; esac; return 1 ;;
  esac
}

free_gb() { df -B1G --output=avail "$(_nearest_dir "$1")" 2>/dev/null | tail -1 | tr -d ' '; }

fast_disk() {
  local d
  for d in $NOCTRAOS_DISK_CANDIDATES; do
    [ -d "$d" ] && [ -w "$d" ] && linux_fs "$d" && [ "$(free_gb "$d")" -ge "$NOCTRAOS_MIN_FREE_GB" ] && { printf '%s' "$d"; return 0; }
  done
  echo "disks.sh: no candidate disk ($NOCTRAOS_DISK_CANDIDATES) is a writable Linux filesystem with ${NOCTRAOS_MIN_FREE_GB} GB free; using \$HOME" >&2
  printf '%s' "$HOME"
}

fast_dir() { printf '%s/%s' "$(fast_disk)" "$1"; }

require_linux_fs() {
  linux_fs "$1" || { echo "$1 must be on a Linux filesystem (ext4, xfs, btrfs), not NTFS/FAT/exFAT: the VM disk and the unpacked system need real permissions and fast IO" >&2; return 1; }
}

require_free_gb() {
  local have; have="$(free_gb "$1")"
  [ "${have:-0}" -ge "$2" ] || { echo "only ${have:-0} GB free for $1, need $2 GB: free space (offload cold data to another drive) or point it at a bigger disk" >&2; return 1; }
}
