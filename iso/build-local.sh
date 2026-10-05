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
#   work.img                           a sparse 40 GB ext4 image, loop-mounted inside the container
#
# Why a container: the build needs root (loop mount, chroot) and xorriso, and a workstation may have
# no passwordless sudo. Why an image file: the work directory must be a real Linux filesystem (the
# unpacked system has symlinks, device nodes and ownership); an NTFS drive cannot hold it, so an
# ext4 image file on that drive is loop-mounted INSIDE the container. --privileged is only for that
# mount. Everything is built from a fresh clone of GitHub main (REPO_URL to override), exactly
# like the first-boot runner, so push first.
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
if [ ! -f "$DIR/work.img" ]; then
  truncate -s 40G "$DIR/work.img"
  mkfs.ext4 -F -q -L noctraos-work "$DIR/work.img"
fi

# The script that runs INSIDE the container.
cat > "$DIR/run-build.sh" <<'INNER'
#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p /work
mount -o loop /host/work.img /work
trap 'cd /; umount /work 2>/dev/null || true' EXIT
rm -rf /work/src /work/tmp   # the image is reused between runs: start from a clean tree
git clone -q --depth 1 "${REPO_URL:-https://github.com/dazeb/noctraos.git}" /work/src
git -C /work/src log -1 --format="building main at %h %s"
VERSION="$(tr -d '[:space:]' < /work/src/VERSION)"
export WORK_BASE=/work/tmp; mkdir -p "$WORK_BASE"
BASE=/host/in/Zorin-OS-18.1-Core-64-bit.iso
BUILD=/work/src/iso/build-noctraos-iso.sh

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

docker run --rm --privileged -e WHAT="$WHAT" ${REPO_URL:+-e REPO_URL="$REPO_URL"} -v "$DIR:/host" "$IMAGE" \
  bash /host/run-build.sh
ls -lh "$DIR/out"
