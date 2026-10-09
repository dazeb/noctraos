#!/usr/bin/env bash
# build-noctraos-iso.sh — remaster a Zorin OS live ISO into "NoctraOS".
#
# What it does:
#   1. extracts the Zorin live ISO tree (xorriso osirrox)
#   2. unpacks casper/filesystem.squashfs
#   3. injects:
#        /opt/noctraos                     snapshot of this provisioner repo
#        /usr/local/sbin/noctraos-firstboot  first-boot runner (as the user)
#        /etc/skel/.config/autostart/...   autostart entry that runs it on
#                                          the user's first desktop login
#        boot menus (BIOS isolinux + UEFI grub), live-boot splash, installed
#        splash/GRUB theme and the dark installer session (iso/boot-theme.sh)
#        .disk/info rebranded to "NoctraOS"
#   4. repacks the squashfs with the original compressor
#   5. writes a new ISO with xorriso, replaying the original boot equipment
#      (BIOS + EFI, same volume id), and refreshes filesystem.size/md5sum.txt
#
# Usage:  sudo ./build-noctraos-iso.sh <zorin-live.iso> [out.iso]
# Needs:  xorriso, squashfs-tools, git, openssl, ~25 GiB scratch (set WORK_BASE).
#
# Unattended installer (Ubiquity preseeding), only with NOCTRAOS_UNATTENDED=1: a seed
# generated from iso/preseed/noctraos.seed.in is baked at /preseed/noctraos.seed and
# an "Install NoctraOS (unattended)" entry becomes the default (5 s timeout) in both
# the BIOS (isolinux) and UEFI (grub) menus, so a fresh VM installs fully hands-off.
# Without it (a release build) the ISO carries no seed, no password hash and no such
# entry: it is the interactive installer only.
#
# Build-time knobs (env):
#   NOCTRAOS_UNATTENDED  1 = boot straight into the unattended install (default 0)
#   NOCTRAOS_AUTOLOGIN   1 = auto-login the created user at first boot so the
#                        provisioner runs with zero interaction (default: 1
#                        when NOCTRAOS_UNATTENDED=1, else 0). This also bypasses
#                        a known issue on this image: the GDM *greeter* session
#                        fails to start (gnome-session can't resolve its
#                        components); user sessions work fine.
#   NOCTRAOS_USER        account to create            (default noctraos)
#   NOCTRAOS_FULLNAME    GECOS full name              (default "NoctraOS User")
#   NOCTRAOS_HOSTNAME    installed hostname           (default noctraos)
#   NOCTRAOS_PASSWORD    plaintext, hashed at build   (default noctraos)
#   NOCTRAOS_LOCALE      (default en_US.UTF-8)
#   NOCTRAOS_KEYMAP      console layout code          (default us)
#   NOCTRAOS_TIMEZONE    (default UTC)
#   NOCTRAOS_BRANCH      provisioner branch (default main; nightly builds use nightly)
#
# The seed carries the password hash — anyone with the ISO can read it.
# Only bake throwaway credentials.
set -Eeuo pipefail

SRC_ISO="${1:?usage: build-noctraos-iso.sh <zorin-live.iso> [out.iso]}"
OUT_ISO="${2:-noctraos-amd64.iso}"
REPO="${REPO_URL:-https://github.com/dazeb/noctraos.git}"
BRANCH="${NOCTRAOS_BRANCH:-main}"   # provisioner branch baked in AND fetched at first boot (nightly builds)
WORK_BASE="${WORK_BASE:-/var/tmp}"

UNATTENDED="${NOCTRAOS_UNATTENDED:-0}"
AUTOLOGIN="${NOCTRAOS_AUTOLOGIN:-$UNATTENDED}"
AI_USER="${NOCTRAOS_USER:-noctraos}"
AI_FULLNAME="${NOCTRAOS_FULLNAME:-NoctraOS User}"
AI_HOSTNAME="${NOCTRAOS_HOSTNAME:-noctraos}"
AI_PASSWORD="${NOCTRAOS_PASSWORD:-noctraos}"
AI_LOCALE="${NOCTRAOS_LOCALE:-en_US.UTF-8}"
AI_KEYMAP="${NOCTRAOS_KEYMAP:-us}"
AI_TIMEZONE="${NOCTRAOS_TIMEZONE:-UTC}"
SEED_TEMPLATE="$(cd "$(dirname "$0")" && pwd)/preseed/noctraos.seed.in"
# shellcheck source=iso/boot-theme.sh
source "$(cd "$(dirname "$0")" && pwd)/boot-theme.sh"
# shellcheck source=iso/strip-census.sh
source "$(cd "$(dirname "$0")" && pwd)/strip-census.sh"
# shellcheck source=iso/rebrand-labels.sh
source "$(cd "$(dirname "$0")" && pwd)/rebrand-labels.sh"
# shellcheck source=iso/bake-shell.sh
source "$(cd "$(dirname "$0")" && pwd)/bake-shell.sh"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }; }
need xorriso; need unsquashfs; need mksquashfs; need git; need openssl
need python3; need zstd; need cpio; need update-alternatives; need chroot
[ -f "$SEED_TEMPLATE" ] || { echo "missing preseed template: $SEED_TEMPLATE" >&2; exit 1; }

WORK="$(mktemp -d "$WORK_BASE/noctraos-iso-build.XXXXXXXX")"
ISO_TREE="$WORK/iso"
SQ_ROOT="$WORK/squashfs-root"
trap 'echo "work dir kept for inspection: $WORK (remove with rm -rf)"' EXIT
mkdir -p "$ISO_TREE" "$SQ_ROOT"

step() { printf '\n\033[1;36m[noctraos-iso]\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "run as root (squashfs device nodes need it)" >&2; exit 1; }
[ -f "$SRC_ISO" ] || { echo "no such ISO: $SRC_ISO" >&2; exit 1; }

step "1/7 extracting ISO tree"
xorriso -osirrox on -indev "$SRC_ISO" -extract / "$ISO_TREE" >/dev/null 2>&1
[ -f "$ISO_TREE/casper/filesystem.squashfs" ] || {
  echo "unexpected layout: casper/filesystem.squashfs not found" >&2; exit 1; }

step "2/7 reading squashfs parameters"
SQ_INFO="$(unsquashfs -s "$ISO_TREE/casper/filesystem.squashfs")"
COMP="$(awk '/Compression / && !/Parameters/ {print $2; exit}' <<<"$SQ_INFO")"
[ -n "$COMP" ] || { echo "could not detect squashfs compressor" >&2; exit 1; }
echo "original compressor: $COMP"

step "3/7 unpacking squashfs (this takes a few minutes)"
unsquashfs -no-progress -d "$SQ_ROOT" "$ISO_TREE/casper/filesystem.squashfs" >/dev/null
# Owners and groups must survive the round trip: the D-Bus launch helper is root:messagebus (4754), and as root:root the bus
# cannot run it, so the Software Updater's apt daemon never starts. A build without CAP_CHOWN (rootless, a user namespace)
# silently extracts everything as root, so check one file whose group is not root before going on.
helper_gid="$(stat -c %g "$SQ_ROOT/usr/lib/dbus-1.0/dbus-daemon-launch-helper" 2>/dev/null || echo 0)"
[ "$helper_gid" != 0 ] || {
  echo "unpacking lost file ownership (dbus-daemon-launch-helper is group root): build as real root with CAP_CHOWN" >&2; exit 1; }

step "4/7 injecting provisioner"
rm -rf "$SQ_ROOT/opt/noctraos"
git clone --depth 1 --branch "$BRANCH" "$REPO" "$SQ_ROOT/opt/noctraos" >/dev/null 2>&1
# The snapshot loses its .git, but first boot falls back to it when there is no git/network: keep the commit it
# is, so a release build can still prove which commit the provisioned VM ran (iso/vm-image.sh reads this file).
git -C "$SQ_ROOT/opt/noctraos" rev-parse HEAD > "$SQ_ROOT/opt/noctraos/.noctraos-commit"
rm -rf "$SQ_ROOT/opt/noctraos/.git"

# The release version comes from the provisioner snapshot (VERSION), never from the
# Zorin base ISO (whose "18.1" is the upstream version, not ours).
RELEASE_VERSION="$(tr -d '[:space:]' < "$SQ_ROOT/opt/noctraos/VERSION" 2>/dev/null || true)"
[ -n "$RELEASE_VERSION" ] || { echo "ERROR: VERSION file missing from the provisioner snapshot" >&2; exit 1; }
step "release version: $RELEASE_VERSION"
mkdir -p "$SQ_ROOT/etc"
printf 'NOCTRAOS_VERSION=%s\nNOCTRAOS_BASE="Zorin OS 18.1 (Ubuntu 24.04)"\n' \
  "$RELEASE_VERSION" > "$SQ_ROOT/etc/noctraos-release"

mkdir -p "$SQ_ROOT/usr/local/sbin" "$SQ_ROOT/etc/skel/.config/autostart"

cat > "$SQ_ROOT/usr/local/sbin/noctraos-firstboot" <<'EOF'
#!/usr/bin/env bash
# noctraos first-boot provisioning — launched by the user's autostart entry.
# Prefers a fresh clone from GitHub; falls back to the baked-in snapshot.
set -u
DEST="$HOME/.local/share/noctraos"
MARKER="$DEST/.provisioned"
AUTOSTART="$HOME/.config/autostart/noctraos-setup.desktop"
LOG="$DEST-firstboot.log"
REPO_URL="https://github.com/dazeb/noctraos.git"
REPO_BRANCH="__NOCTRAOS_BRANCH__"   # substituted at ISO build time

if [ -f "$MARKER" ]; then rm -f "$AUTOSTART"; exit 0; fi
mkdir -p "$HOME/.local/share" "$(dirname "$LOG")"
echo "======================================================"
echo "  noctraos :: setting up your AI workstation"
echo "  (you will be asked for your password to install software)"
echo "======================================================"

rm -rf "$DEST"
if command -v git >/dev/null 2>&1 \
   && curl -fsSI --max-time 8 https://github.com >/dev/null 2>&1 \
   && git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$DEST" >/dev/null 2>&1; then
  echo "noctraos: provisioner fetched from GitHub (latest)"
else
  cp -r /opt/noctraos "$DEST"
  echo "noctraos: using the provisioner snapshot baked into this ISO"
fi

cd "$DEST"
# The welcome app runs while provisioning runs, so the wait becomes learning.
if [ -f "$DEST/bin/noctraos-welcome" ] && command -v python3 >/dev/null 2>&1; then
  ( setsid python3 "$DEST/bin/noctraos-welcome" --provisioning >/dev/null 2>&1 & )
fi
bash install.sh 2>&1 | tee "$LOG"
STATUS="${PIPESTATUS[0]}"
if [ "$STATUS" -eq 0 ]; then
  touch "$MARKER"
  rm -f "$AUTOSTART"
  echo "noctraos: setup complete — welcome aboard."
  echo "  Health check: noc doctor    GUI panel: noctraos-control"
else
  echo "noctraos: setup hit an error (exit $STATUS)."
  echo "  Log: $LOG    Re-run with: bash $DEST/install.sh"
fi
read -r -n 1 -s -p "Press any key to close this window..."
EOF
sed -i "s|__NOCTRAOS_BRANCH__|$BRANCH|" "$SQ_ROOT/usr/local/sbin/noctraos-firstboot"
chmod 755 "$SQ_ROOT/usr/local/sbin/noctraos-firstboot"

cat > "$SQ_ROOT/etc/skel/.config/autostart/noctraos-setup.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=noctraos Setup
Comment=One-time setup of your AI developer workstation
Exec=/usr/local/sbin/noctraos-firstboot
Terminal=true
Categories=System;
X-GNOME-Autostart-enabled=true
NoDisplay=false
EOF

if [ "$AUTOLOGIN" = 1 ]; then
  mkdir -p "$SQ_ROOT/etc/gdm3"
  cat > "$SQ_ROOT/etc/gdm3/custom.conf" <<EOF
[daemon]
AutomaticLoginEnable=True
AutomaticLogin=$AI_USER

[security]

[xdmcp]

[chooser]

[debug]
EOF
  # Appliance semantics: with autologin there is nobody to re-type the sudo
  # password when the firstboot provisioner's credential cache expires.
  mkdir -p "$SQ_ROOT/etc/sudoers.d"
  cat > "$SQ_ROOT/etc/sudoers.d/90-noctraos-firstboot" <<EOF
$AI_USER ALL=(ALL) NOPASSWD:ALL
EOF
  chmod 440 "$SQ_ROOT/etc/sudoers.d/90-noctraos-firstboot"
fi

# --- unattended preseed: bake the seed, add the boot entries ---------------
# Only in NOCTRAOS_UNATTENDED=1 builds. A release ISO carries neither the seed
# (it holds a password hash) nor a boot entry that installs and wipes the disk
# without asking.
SEED_MAP=()
if [ "$UNATTENDED" = 1 ]; then
  step "4/7 generating unattended preseed seed"
  mkdir -p "$ISO_TREE/preseed"
  # sha512-crypt alphabet is [./0-9A-Za-z$] — no sed metachars for the | delimiter.
  PASSWORD_CRYPT="$(openssl passwd -6 "$AI_PASSWORD")"
  sed -e "s|@LOCALE@|$AI_LOCALE|g" \
      -e "s|@KEYMAP@|$AI_KEYMAP|g" \
      -e "s|@TIMEZONE@|$AI_TIMEZONE|g" \
      -e "s|@HOSTNAME@|$AI_HOSTNAME|g" \
      -e "s|@USERNAME@|$AI_USER|g" \
      -e "s|@FULLNAME@|$AI_FULLNAME|g" \
      -e "s|@PASSWORD_CRYPT@|$PASSWORD_CRYPT|g" \
      "$SEED_TEMPLATE" > "$ISO_TREE/preseed/noctraos.seed"
  chmod 644 "$ISO_TREE/preseed/noctraos.seed"
  SEED_MAP=(-map "$ISO_TREE/preseed/noctraos.seed" /preseed/noctraos.seed)
fi

step "4/7 theming the boot chain (grub, isolinux, live splash, installed system)"
boot_theme_iso_tree "$ISO_TREE"
boot_theme_initrd "$ISO_TREE"
boot_theme_squashfs "$SQ_ROOT"
strip_census "$SQ_ROOT"
rebrand_labels "$SQ_ROOT" "$RELEASE_VERSION"
bake_shell "$SQ_ROOT" "$SQ_ROOT/opt/noctraos"

if [ "$UNATTENDED" = 1 ]; then
step "4/7 adding unattended boot entries (BIOS isolinux + UEFI grub)"
# noprompt: casper-stop ejects the medium and reboots without the
# "Please remove the installation medium, then press ENTER" wait.
SEED_ARGS="file=/cdrom/preseed/noctraos.seed auto=true priority=critical automatic-ubiquity noprompt"

GRUB_ENTRY="menuentry \"Install NoctraOS (unattended)\" --class zorin {
	set gfxpayload=keep
	linux	/casper/vmlinuz maybe-ubiquity $SEED_ARGS quiet splash ---
	initrd	/casper/initrd.zstd
}"
# default entry: prepend before the first menuentry, shorten the timeout
sed -i 's/^set timeout=[0-9]\+/set timeout=5/' "$ISO_TREE/boot/grub/grub.cfg"
awk -v e="$GRUB_ENTRY" '!d && /^menuentry / { print e; print ""; d=1 } { print }' \
  "$ISO_TREE/boot/grub/grub.cfg" > "$ISO_TREE/boot/grub/grub.cfg.new" \
  && mv "$ISO_TREE/boot/grub/grub.cfg.new" "$ISO_TREE/boot/grub/grub.cfg"

cat >> "$ISO_TREE/isolinux/menuentries.cfg" <<EOF
MENU SEPARATOR

LABEL unattended
  MENU LABEL ^Install NoctraOS (unattended)
  MENU DEFAULT
  KERNEL /casper/vmlinuz
  APPEND maybe-ubiquity initrd=/casper/initrd.zstd $SEED_ARGS quiet splash ---
EOF
# DEFAULT lives in menuentries.cfg; TIMEOUT (1/10 s units, 50 => 5 s) in isolinux.cfg
sed -i 's/^DEFAULT live/DEFAULT unattended/' "$ISO_TREE/isolinux/menuentries.cfg"
sed -i 's/^TIMEOUT [0-9]\+/TIMEOUT 50/' "$ISO_TREE/isolinux/isolinux.cfg"
fi

if [ -f "$ISO_TREE/.disk/info" ]; then
  # The installer builds "Try/Install <name>" from the first word of this line
  # (the stock file reads "Zorin-OS 18.1 Core 64bit"). Replace the whole line so
  # the version shown is ours, not the base distro's.
  echo "NoctraOS $RELEASE_VERSION 64bit" > "$ISO_TREE/.disk/info"
fi
chown -R root:root "$SQ_ROOT/opt/noctraos" "$SQ_ROOT/usr/local/sbin/noctraos-firstboot" \
  "$SQ_ROOT/etc/skel/.config/autostart"

step "5/7 repacking squashfs ($COMP — this is the long step)"
# No -all-root: it flattened every file to root:root (and broke the Software Updater, see migrations/system/0001).
mksquashfs "$SQ_ROOT" "$WORK/filesystem.squashfs" -comp "$COMP" -noappend \
  -no-progress -info >/dev/null
# Prove the image kept the owners: the launch helper must not be 0/0 in what we are about to ship.
helper_owner="$(unsquashfs -lln "$WORK/filesystem.squashfs" usr/lib/dbus-1.0/dbus-daemon-launch-helper 2>/dev/null \
  | awk '/dbus-daemon-launch-helper/ {print $2; exit}')"
[ -n "$helper_owner" ] && [ "$helper_owner" != "0/0" ] || {
  echo "the repacked squashfs lost file ownership (launch helper owner: ${helper_owner:-missing})" >&2; exit 1; }

step "6/7 refreshing ISO metadata"
# casper-md5check runs on every live boot against /cdrom/md5sum.txt (singular) and
# reports "errors found" for any file that differs, so the list must describe the
# files that actually ship — including the new squashfs, not the extracted original.
mv "$WORK/filesystem.squashfs" "$ISO_TREE/casper/filesystem.squashfs"
stat -c %s "$ISO_TREE/casper/filesystem.squashfs" > "$ISO_TREE/casper/filesystem.size"
# Excluded like the stock list: the file itself (and its temp), boot.cat, and
# isolinux.bin, which xorriso patches (boot-info-table) while writing the image.
( cd "$ISO_TREE" && find . -type f ! -name 'md5sum.txt*' ! -name boot.cat ! -name isolinux.bin -print0 \
    | xargs -0 md5sum > ../md5sum.new && mv ../md5sum.new md5sum.txt )

step "7/7 writing $OUT_ISO (boot equipment replayed from source ISO)"
# xorriso refuses to overwrite a non-empty -outdev — remove the previous image.
rm -f "$OUT_ISO"
xorriso -indev "$SRC_ISO" \
  -outdev "$OUT_ISO" \
  -boot_image any replay \
  -volid "NOCTRAOS_${RELEASE_VERSION//./_}" \
  -map "$ISO_TREE/casper/filesystem.squashfs" /casper/filesystem.squashfs \
  -map "$ISO_TREE/casper/filesystem.size" /casper/filesystem.size \
  -map "$ISO_TREE/md5sum.txt" /md5sum.txt \
  -map "$ISO_TREE/boot/grub/grub.cfg" /boot/grub/grub.cfg \
  -map "$ISO_TREE/boot/grub/themes/noctraos" /boot/grub/themes/noctraos \
  -map "$ISO_TREE/casper/initrd.zstd" /casper/initrd.zstd \
  -map "$ISO_TREE/isolinux/splash.png" /isolinux/splash.png \
  "${SEED_MAP[@]}" \
  -map "$ISO_TREE/isolinux/menuentries.cfg" /isolinux/menuentries.cfg \
  -map "$ISO_TREE/isolinux/isolinux.cfg" /isolinux/isolinux.cfg \
  -map "$ISO_TREE/.disk/info" /.disk/info \
  -padding 0

step "done"
ls -lh "$OUT_ISO"
sha256sum "$OUT_ISO" | tee "$OUT_ISO.sha256"
echo "work dir: $WORK (safe to rm -rf)"
