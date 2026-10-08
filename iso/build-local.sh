#!/usr/bin/env bash
# build-local.sh — build the NoctraOS ISO(s) on a fast workstation, in a privileged Docker
# container, with the work directory on a big drive. About 2 minutes per ISO on NVMe.
#
#   iso/build-local.sh <dir> [release|appliance|both]       (default: release)
#
# <dir> layout (created as needed):
#   in/Zorin-OS-18.1-Core-64-bit.iso   the base ISO. Put it there once (the Proxmox node has a copy
#                                      in /var/lib/vz/template/iso/).
#   out/                               results: noctraos-<VERSION>-amd64.iso (+ .sha256) and, for
#                                      `appliance`, noctraos-<VERSION>-appliance-build.iso
#   work/                              scratch, removed when the build ends (ext4/xfs/btrfs/zfs drives)
#   work.img                           only on a drive that is not a Linux filesystem: see below
#
# Why a container: the build needs root (unsquashfs keeps ownership and device nodes) and xorriso, and a
# workstation may have no passwordless sudo. The work directory must be a real Linux filesystem (the unpacked
# system has symlinks, device nodes and ownership). On one (the 2 TB build drive is ext4 now) the container builds
# straight into <dir>/work and runs unprivileged-by-default (no --privileged). On NTFS/exFAT/FAT, which cannot hold
# it, a sparse ext4 image file is loop-mounted INSIDE the container instead, and only that needs --privileged;
# BUILD_USE_IMAGE=1 forces this path. Everything is built from a fresh clone of GitHub main (REPO_URL to override, and
# NOCTRAOS_BRANCH=nightly for the nightly image), exactly like the first-boot runner, so push first.
#
#   release    interactive installer: no seed, no password hash, no unattended boot entry. This is
#              the ISO that gets published. The run FAILS if any of that is found in it.
#   appliance  unattended install, user noctraos / password noctraos, autologin + passwordless sudo.
#              Only a means to build the downloadable VM disk; never publish it.
set -Eeuo pipefail

DIR="${1:?usage: build-local.sh <dir> [release|appliance|both]}"
WHAT="${2:-release}"
DIR="$(cd "$DIR" 2>/dev/null && pwd || { mkdir -p "$DIR" && cd "$DIR" && pwd; })"
BASE="Zorin-OS-18.1-Core-64-bit.iso"
IMAGE="${BUILDER_IMAGE:-noctraos-iso-builder}"
case "$WHAT" in release|appliance|both) ;; *) echo "unknown target: $WHAT" >&2; exit 1 ;; esac

mkdir -p "$DIR/in" "$DIR/out" "$DIR/ctx"
[ -f "$DIR/in/$BASE" ] || { echo "missing $DIR/in/$BASE (copy the base ISO there first)" >&2; exit 1; }

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  cat > "$DIR/ctx/Dockerfile" <<'DOCKERFILE'
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
      xorriso squashfs-tools git openssl zstd cpio python3 util-linux e2fsprogs \
      ca-certificates curl coreutils dpkg findutils sed gawk grep \
    && rm -rf /var/lib/apt/lists/*
DOCKERFILE
  docker build -q -t "$IMAGE" "$DIR/ctx"
fi
# A real Linux filesystem can hold the unpacked system directly; anything else needs the loop-mounted image.
case "$(stat -f -c %T "$DIR")" in
  ext2/ext3|ext4|xfs|btrfs|zfs) DIRECT=1 ;;
  *) DIRECT=0 ;;
esac
[ -z "${BUILD_USE_IMAGE:-}" ] || DIRECT=0
if [ "$DIRECT" = 0 ] && [ ! -f "$DIR/work.img" ]; then
  truncate -s 40G "$DIR/work.img"
  mkfs.ext4 -F -q -L noctraos-work "$DIR/work.img"
fi

# The script that runs INSIDE the container.
cat > "$DIR/run-build.sh" <<'INNER'
#!/usr/bin/env bash
set -Eeuo pipefail
if [ "$DIRECT" = 1 ]; then
  WORK=/host/work
  mkdir -p "$WORK"
  trap 'cd /; rm -rf "$WORK"' EXIT   # root-owned scratch (unpacked system): the host user could not delete it
else
  WORK=/work
  mkdir -p "$WORK"
  mount -o loop /host/work.img "$WORK"
  trap 'cd /; umount "$WORK" 2>/dev/null || true' EXIT
fi
git config --global --add safe.directory '*'   # a REPO_URL=file:// clone is owned by the host user
rm -rf "$WORK/src" "$WORK/tmp"   # start from a clean tree
git clone -q --depth 1 --branch "${NOCTRAOS_BRANCH:-main}" "${REPO_URL:-https://github.com/dazeb/noctraos.git}" "$WORK/src"
git -C "$WORK/src" log -1 --format="building ${NOCTRAOS_BRANCH:-main} at %h %s"
VERSION="$(tr -d '[:space:]' < "$WORK/src/VERSION")"
export WORK_BASE="$WORK/tmp"; mkdir -p "$WORK_BASE"
BASE=/host/in/Zorin-OS-18.1-Core-64-bit.iso
BUILD="$WORK/src/iso/build-noctraos-iso.sh"

if [ "$WHAT" = release ] || [ "$WHAT" = both ]; then
  OUT=/host/out/noctraos-$VERSION-amd64.iso
  echo "=== release ISO (interactive) $(date +%H:%M)"
  nice -n 10 bash "$BUILD" "$BASE" "$OUT"
  rm -rf "$WORK_BASE"/noctraos-iso-build.*
  echo "=== checking the release ISO"
  fail=0
  vol="$(xorriso -indev "$OUT" -report_system_area plain 2>&1 | sed -n "s/^Volume id *: '\(.*\)'/\1/p")"
  [ "$vol" = "NOCTRAOS_${VERSION//./_}" ] || { echo "FAIL: volume id is '$vol'"; fail=1; }
  xorriso -osirrox on -indev "$OUT" -extract /boot/grub/grub.cfg /tmp/grub.cfg >/dev/null 2>&1
  xorriso -osirrox on -indev "$OUT" -extract /isolinux/menuentries.cfg /tmp/menu.cfg >/dev/null 2>&1
  grep -qiE 'unattended|noctraos\.seed' /tmp/grub.cfg /tmp/menu.cfg && { echo "FAIL: an unattended boot entry is in the release ISO"; fail=1; }
  xorriso -indev "$OUT" -find /preseed -name 'noctraos.seed' 2>/dev/null | grep -q noctraos.seed && { echo "FAIL: the preseed seed is in the release ISO"; fail=1; }
  grep -q 'menuentry "Try or Install NoctraOS"' /tmp/grub.cfg || { echo "FAIL: default boot entry missing"; fail=1; }
  [ "$fail" -eq 0 ] || exit 1
  echo "release ISO checks passed (volume id $vol, no seed, no unattended entry)"
fi

if [ "$WHAT" = appliance ] || [ "$WHAT" = both ]; then
  echo "=== appliance ISO (unattended, user noctraos) $(date +%H:%M)"
  NOCTRAOS_UNATTENDED=1 NOCTRAOS_USER=noctraos NOCTRAOS_PASSWORD=noctraos NOCTRAOS_HOSTNAME=noctraos \
    nice -n 10 bash "$BUILD" "$BASE" "/host/out/noctraos-$VERSION-appliance-build.iso"
  rm -rf "$WORK_BASE"/noctraos-iso-build.*
fi
echo "=== ALL DONE $(date +%H:%M)"
INNER

PRIV=(); [ "$DIRECT" = 1 ] || PRIV=(--privileged)
docker run --rm "${PRIV[@]}" -e WHAT="$WHAT" -e DIRECT="$DIRECT" ${REPO_URL:+-e REPO_URL="$REPO_URL"} ${NOCTRAOS_BRANCH:+-e NOCTRAOS_BRANCH="$NOCTRAOS_BRANCH"} -v "$DIR:/host" "$IMAGE" \
  bash /host/run-build.sh
ls -lh "$DIR/out"
