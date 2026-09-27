#!/usr/bin/env bash
# build-zorin-ai-iso.sh — remaster a Zorin OS live ISO into "Zorin-AI OS".
#
# What it does:
#   1. extracts the Zorin live ISO tree (xorriso osirrox)
#   2. unpacks casper/filesystem.squashfs
#   3. injects:
#        /opt/zorin-ai                     snapshot of this provisioner repo
#        /usr/local/sbin/zorin-ai-firstboot  first-boot runner (as the user)
#        /etc/skel/.config/autostart/...   autostart entry that runs it on
#                                          the user's first desktop login
#        boot menu + .disk/info rebranded to "Zorin-AI OS"
#   4. repacks the squashfs with the original compressor
#   5. writes a new ISO with xorriso, replaying the original boot equipment
#      (BIOS + EFI, same volume id), and refreshes filesystem.size/md5sums.txt
#
# Usage:  sudo ./build-zorin-ai-iso.sh <zorin-live.iso> [out.iso]
# Needs:  xorriso, squashfs-tools, git, openssl, ~25 GiB scratch (set WORK_BASE).
#
# Unattended installer (Ubiquity preseeding): a seed generated from
# iso/preseed/zorin-ai.seed.in is baked at /preseed/zorin-ai.seed and an
# "Install Zorin-AI OS (unattended)" boot entry is added to both the BIOS
# (isolinux) and UEFI (grub) menus. Set ZORIN_AI_UNATTENDED=1 to make it the
# default (5 s timeout) so a fresh VM installs fully hands-off.
#
# Build-time knobs (env):
#   ZORIN_AI_UNATTENDED  1 = boot straight into the unattended install (default 0)
#   ZORIN_AI_AUTOLOGIN   1 = auto-login the created user at first boot so the
#                        provisioner runs with zero interaction (default: 1
#                        when ZORIN_AI_UNATTENDED=1, else 0). This also bypasses
#                        a known issue on this image: the GDM *greeter* session
#                        fails to start (gnome-session can't resolve its
#                        components); user sessions work fine.
#   ZORIN_AI_USER        account to create            (default zorin)
#   ZORIN_AI_FULLNAME    GECOS full name              (default "Zorin-AI User")
#   ZORIN_AI_HOSTNAME    installed hostname           (default zorin-ai)
#   ZORIN_AI_PASSWORD    plaintext, hashed at build   (default zorin-ai)
#   ZORIN_AI_LOCALE      (default en_US.UTF-8)
#   ZORIN_AI_KEYMAP      console layout code          (default us)
#   ZORIN_AI_TIMEZONE    (default UTC)
#
# The seed carries the password hash — anyone with the ISO can read it.
# Only bake throwaway credentials.
set -Eeuo pipefail

SRC_ISO="${1:?usage: build-zorin-ai-iso.sh <zorin-live.iso> [out.iso]}"
OUT_ISO="${2:-zorin-ai-os-amd64.iso}"
REPO="${REPO_URL:-https://github.com/dazeb/zorin-ai.git}"
WORK_BASE="${WORK_BASE:-/var/tmp}"

UNATTENDED="${ZORIN_AI_UNATTENDED:-0}"
AUTOLOGIN="${ZORIN_AI_AUTOLOGIN:-$UNATTENDED}"
AI_USER="${ZORIN_AI_USER:-zorin}"
AI_FULLNAME="${ZORIN_AI_FULLNAME:-Zorin-AI User}"
AI_HOSTNAME="${ZORIN_AI_HOSTNAME:-zorin-ai}"
AI_PASSWORD="${ZORIN_AI_PASSWORD:-zorin-ai}"
AI_LOCALE="${ZORIN_AI_LOCALE:-en_US.UTF-8}"
AI_KEYMAP="${ZORIN_AI_KEYMAP:-us}"
AI_TIMEZONE="${ZORIN_AI_TIMEZONE:-UTC}"
SEED_TEMPLATE="$(cd "$(dirname "$0")" && pwd)/preseed/zorin-ai.seed.in"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }; }
need xorriso; need unsquashfs; need mksquashfs; need git; need openssl
[ -f "$SEED_TEMPLATE" ] || { echo "missing preseed template: $SEED_TEMPLATE" >&2; exit 1; }

WORK="$(mktemp -d "$WORK_BASE/zorin-ai-iso-build.XXXXXXXX")"
ISO_TREE="$WORK/iso"
SQ_ROOT="$WORK/squashfs-root"
trap 'echo "work dir kept for inspection: $WORK (remove with rm -rf)"' EXIT
mkdir -p "$ISO_TREE" "$SQ_ROOT"

step() { printf '\n\033[1;36m[zorin-ai-iso]\033[0m %s\n' "$*"; }

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

step "4/7 injecting provisioner"
rm -rf "$SQ_ROOT/opt/zorin-ai"
git clone --depth 1 "$REPO" "$SQ_ROOT/opt/zorin-ai" >/dev/null 2>&1
rm -rf "$SQ_ROOT/opt/zorin-ai/.git"

mkdir -p "$SQ_ROOT/usr/local/sbin" "$SQ_ROOT/etc/skel/.config/autostart"

cat > "$SQ_ROOT/usr/local/sbin/zorin-ai-firstboot" <<'EOF'
#!/usr/bin/env bash
# zorin-ai first-boot provisioning — launched by the user's autostart entry.
# Prefers a fresh clone from GitHub; falls back to the baked-in snapshot.
set -u
DEST="$HOME/.local/share/zorin-ai"
MARKER="$DEST/.provisioned"
AUTOSTART="$HOME/.config/autostart/zorin-ai-setup.desktop"
LOG="$DEST-firstboot.log"
REPO_URL="https://github.com/dazeb/zorin-ai.git"

if [ -f "$MARKER" ]; then rm -f "$AUTOSTART"; exit 0; fi
mkdir -p "$HOME/.local/share" "$(dirname "$LOG")"
echo "======================================================"
echo "  zorin-ai :: setting up your AI workstation"
echo "  (you will be asked for your password to install software)"
echo "======================================================"

rm -rf "$DEST"
if command -v git >/dev/null 2>&1 \
   && curl -fsSI --max-time 8 https://github.com >/dev/null 2>&1 \
   && git clone --depth 1 "$REPO_URL" "$DEST" >/dev/null 2>&1; then
  echo "zorin-ai: provisioner fetched from GitHub (latest)"
else
  cp -r /opt/zorin-ai "$DEST"
  echo "zorin-ai: using the provisioner snapshot baked into this ISO"
fi

cd "$DEST"
bash install.sh 2>&1 | tee "$LOG"
STATUS="${PIPESTATUS[0]}"
if [ "$STATUS" -eq 0 ]; then
  touch "$MARKER"
  rm -f "$AUTOSTART"
  echo "zorin-ai: setup complete — welcome aboard."
  echo "  Health check: zom doctor    GUI panel: zom-menu"
else
  echo "zorin-ai: setup hit an error (exit $STATUS)."
  echo "  Log: $LOG    Re-run with: bash $DEST/install.sh"
fi
read -r -n 1 -s -p "Press any key to close this window..."
EOF
chmod 755 "$SQ_ROOT/usr/local/sbin/zorin-ai-firstboot"

cat > "$SQ_ROOT/etc/skel/.config/autostart/zorin-ai-setup.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=zorin-ai Setup
Comment=One-time setup of your AI developer workstation
Exec=/usr/local/sbin/zorin-ai-firstboot
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
  cat > "$SQ_ROOT/etc/sudoers.d/90-zorin-ai-firstboot" <<EOF
$AI_USER ALL=(ALL) NOPASSWD:ALL
EOF
  chmod 440 "$SQ_ROOT/etc/sudoers.d/90-zorin-ai-firstboot"
fi

# --- unattended preseed: bake the seed, add the boot entries ---------------
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
    "$SEED_TEMPLATE" > "$ISO_TREE/preseed/zorin-ai.seed"
chmod 644 "$ISO_TREE/preseed/zorin-ai.seed"

step "4/7 adding unattended boot entries (BIOS isolinux + UEFI grub)"
if [ -f "$ISO_TREE/boot/grub/grub.cfg" ]; then
  sed -i 's/Try or Install Zorin OS/Try or Install Zorin-AI OS/g' "$ISO_TREE/boot/grub/grub.cfg" || true
fi
# noprompt: casper-stop ejects the medium and reboots without the
# "Please remove the installation medium, then press ENTER" wait.
SEED_ARGS="file=/cdrom/preseed/zorin-ai.seed auto=true priority=critical automatic-ubiquity noprompt"

GRUB_ENTRY="menuentry \"Install Zorin-AI OS (unattended)\" --class zorin {
	set gfxpayload=keep
	linux	/casper/vmlinuz maybe-ubiquity $SEED_ARGS quiet splash ---
	initrd	/casper/initrd.zstd
}"
if [ "$UNATTENDED" = 1 ]; then
  # default entry: prepend before the first menuentry, shorten the timeout
  sed -i 's/^set timeout=[0-9]\+/set timeout=5/' "$ISO_TREE/boot/grub/grub.cfg"
  awk -v e="$GRUB_ENTRY" '!d && /^menuentry / { print e; print ""; d=1 } { print }' \
    "$ISO_TREE/boot/grub/grub.cfg" > "$ISO_TREE/boot/grub/grub.cfg.new" \
    && mv "$ISO_TREE/boot/grub/grub.cfg.new" "$ISO_TREE/boot/grub/grub.cfg"
else
  # selectable but not default: insert before the trailing grub_platform block
  awk -v e="$GRUB_ENTRY" '/^grub_platform/ && !d { print e; print ""; d=1 } { print }' \
    "$ISO_TREE/boot/grub/grub.cfg" > "$ISO_TREE/boot/grub/grub.cfg.new" \
    && mv "$ISO_TREE/boot/grub/grub.cfg.new" "$ISO_TREE/boot/grub/grub.cfg"
fi

ISOLINUX_EXTRA=""
[ "$UNATTENDED" = 1 ] && ISOLINUX_EXTRA='  MENU DEFAULT'
cat >> "$ISO_TREE/isolinux/menuentries.cfg" <<EOF
MENU SEPARATOR

LABEL unattended
  MENU LABEL ^Install Zorin-AI OS (unattended)
$ISOLINUX_EXTRA
  KERNEL /casper/vmlinuz
  APPEND maybe-ubiquity initrd=/casper/initrd.zstd $SEED_ARGS quiet splash ---
EOF
if [ "$UNATTENDED" = 1 ]; then
  # DEFAULT lives in menuentries.cfg; TIMEOUT (1/10 s units, 50 => 5 s) in isolinux.cfg
  sed -i 's/^DEFAULT live/DEFAULT unattended/' "$ISO_TREE/isolinux/menuentries.cfg"
  sed -i 's/^TIMEOUT [0-9]\+/TIMEOUT 50/' "$ISO_TREE/isolinux/isolinux.cfg"
fi

if [ -f "$ISO_TREE/.disk/info" ]; then
  sed -i 's/Zorin OS/Zorin-AI OS/' "$ISO_TREE/.disk/info" || true
fi
chown -R root:root "$SQ_ROOT/opt/zorin-ai" "$SQ_ROOT/usr/local/sbin/zorin-ai-firstboot" \
  "$SQ_ROOT/etc/skel/.config/autostart"

step "5/7 repacking squashfs ($COMP — this is the long step)"
mksquashfs "$SQ_ROOT" "$WORK/filesystem.squashfs" -comp "$COMP" -noappend -all-root \
  -no-progress -info >/dev/null

step "6/7 refreshing ISO metadata"
stat -c %s "$WORK/filesystem.squashfs" > "$ISO_TREE/casper/filesystem.size"
( cd "$ISO_TREE" && find . -type f ! -name md5sums.txt -print0 \
    | xargs -0 md5sum > md5sums.txt.new && mv md5sums.txt.new md5sums.txt )

step "7/7 writing $OUT_ISO (boot equipment replayed from source ISO)"
# xorriso refuses to overwrite a non-empty -outdev — remove the previous image.
rm -f "$OUT_ISO"
xorriso -indev "$SRC_ISO" \
  -outdev "$OUT_ISO" \
  -boot_image any replay \
  -map "$WORK/filesystem.squashfs" /casper/filesystem.squashfs \
  -map "$ISO_TREE/casper/filesystem.size" /casper/filesystem.size \
  -map "$ISO_TREE/md5sums.txt" /md5sums.txt \
  -map "$ISO_TREE/boot/grub/grub.cfg" /boot/grub/grub.cfg \
  -map "$ISO_TREE/preseed/zorin-ai.seed" /preseed/zorin-ai.seed \
  -map "$ISO_TREE/isolinux/menuentries.cfg" /isolinux/menuentries.cfg \
  -map "$ISO_TREE/isolinux/isolinux.cfg" /isolinux/isolinux.cfg \
  -map "$ISO_TREE/.disk/info" /.disk/info \
  -padding 0

step "done"
ls -lh "$OUT_ISO"
sha256sum "$OUT_ISO" | tee "$OUT_ISO.sha256"
echo "work dir: $WORK (safe to rm -rf)"
