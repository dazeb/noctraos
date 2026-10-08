#!/usr/bin/env bash
# fastest-disk.sh — measure the candidate disks and say which should hold VM disks and build scratch.
#
#   iso/fastest-disk.sh [dir...]      default: the candidates in iso/disks.sh. Run it when no build is running.
#
# Writes and reads 6 GiB with direct IO (no page cache) in a temporary file on each disk, twice, and keeps the better write
# (SLC caches and garbage collection make a single run noisy). Prints MB/s and the order to put in NOCTRAOS_DISK_CANDIDATES.
set -Eeuo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=iso/disks.sh
source "$HERE/disks.sh"
DIRS=("$@"); [ ${#DIRS[@]} -gt 0 ] || read -r -a DIRS <<<"$NOCTRAOS_DISK_CANDIDATES"
pgrep -x qemu-system-x86 >/dev/null && echo "warning: a VM is running; the numbers will be low" >&2
mbps() { sed -n 's/.*, \([0-9.]*\) \(GB\|MB\)\/s$/\1 \2/p' | awk '{print ($2=="GB") ? $1*1000 : $1}'; }
results=()
for d in "${DIRS[@]}"; do
  [ -d "$d" ] && [ -w "$d" ] || { echo "skip $d: not a writable directory"; continue; }
  f="$d/.fastest-disk-$$.tmp"; best=0
  for _ in 1 2; do
    w="$(dd if=/dev/zero of="$f" bs=1M count=6144 oflag=direct conv=fdatasync 2>&1 | tail -1 | mbps)"
    [ "${w%.*}" -gt "${best%.*}" ] && best="$w"
  done
  r="$(dd if="$f" of=/dev/null bs=1M iflag=direct 2>&1 | tail -1 | mbps)"
  rm -f "$f"
  printf '%-28s write %6.0f MB/s   read %6.0f MB/s   %s GB free   %s\n' "$d" "$best" "$r" "$(free_gb "$d")" "$(stat -f -c %T "$d")"
  results+=("$best $d")
done
echo "suggested NOCTRAOS_DISK_CANDIDATES (best write first): $(printf '%s\n' "${results[@]}" | sort -rn | awk '{print $2}' | tr '\n' ' ')"
