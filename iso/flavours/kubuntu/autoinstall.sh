#!/usr/bin/env bash
# kubuntu/autoinstall.sh — the unattended install of the kubuntu APPLIANCE ISO (flavour kubuntu). Never in a release ISO.
#
# Calamares has no unattended mode, so the appliance build (iso/flavours/kubuntu.sh with NOCTRAOS_UNATTENDED=1) bakes
# this script into the live system as /usr/local/sbin/noctraos-autoinstall, started by noctraos-autoinstall.service only
# when the kernel command line carries `noctraos.autoinstall` (the appliance ISO's default boot entry). It does what
# Kubuntu's Calamares sequence does (/etc/calamares/settings.conf, read from kubuntu-26.04.1), without the pages:
#   partition (GPT: 512 MiB ESP + ext4, the whole first disk) -> unpackfs (/cdrom/casper/filesystem.squashfs) -> machineid
#   -> fstab -> locale/keyboard/timezone -> users (+ autologin, passwordless sudo: appliance semantics, like the Zorin
#   appliance) -> the live kernel copy -> initramfs -> GRUB (shim + signed GRUB, also at the removable path so the exported
#   disk boots on a host with empty UEFI variables) -> i386 arch -> apt sources (automirror's ubuntu.sources) -> live
#   packages removed (packages.conf) -> reboot.
# The VM it is meant for boots its disk first (iso/local-vm.sh), so the reboot lands in the installed system, whose
# autologin starts the first-boot provisioner. Settings come from /etc/noctraos/autoinstall.conf (AI_USER, AI_PASSWORD_CRYPT,
# AI_HOSTNAME, AI_FULLNAME, AI_LOCALE, AI_TIMEZONE), written by the appliance build; it is not copied to the installed system.
#
# DESTROYS the first disk without asking. That is the point of the appliance ISO and why it is never published.
set -Eeuo pipefail

LOG=/var/log/noctraos-autoinstall.log
exec > >(tee -a "$LOG" > /dev/console) 2>&1
CONF="${NOCTRAOS_AUTOINSTALL_CONF:-/etc/noctraos/autoinstall.conf}"
# shellcheck source=/dev/null
. "$CONF"
: "${AI_USER:?}" "${AI_PASSWORD_CRYPT:?}" "${AI_HOSTNAME:=noctraos}" "${AI_FULLNAME:=NoctraOS}" "${AI_LOCALE:=en_US.UTF-8}" "${AI_TIMEZONE:=Etc/UTC}"
T=/target
SQ=/run/noctraos-autoinstall-squashfs
say() { printf '\n[noctraos-autoinstall] %s\n' "$*"; }
fail() { say "FAILED: $*"; say "log: $LOG"; exit 1; }
trap 'fail "line $LINENO: $BASH_COMMAND"' ERR

# The disk: the first whole disk that is not the live medium, a zram device or read-only.
pick_disk() {
  local name type ro
  while read -r name type ro; do
    [ "$type" = disk ] && [ "$ro" = 0 ] || continue
    case "$name" in /dev/zram*|/dev/loop*|/dev/sr*) continue ;; esac
    findmnt -rno SOURCE /cdrom 2>/dev/null | grep -q "^$name" && continue
    echo "$name"; return 0
  done < <(lsblk -dnpo NAME,TYPE,RO)
  return 1
}
part() { case "$1" in *[0-9]) echo "${1}p$2" ;; *) echo "$1$2" ;; esac; }

DISK="$(pick_disk)" || fail "no disk to install to"
say "installing NoctraOS onto $DISK (everything on it is erased)"
swapoff -a || true
for p in $(lsblk -lnpo NAME "$DISK" | tail -n +2); do umount -q "$p" 2>/dev/null || true; done
wipefs -af "$DISK" >/dev/null
sfdisk -q --wipe always "$DISK" <<'EOF'
label: gpt
size=512MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="EFI system partition"
type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="NoctraOS"
EOF
udevadm settle
ESP="$(part "$DISK" 1)"; ROOT="$(part "$DISK" 2)"
mkfs.fat -F 32 -n EFI "$ESP" >/dev/null
mkfs.ext4 -F -q -L noctraos "$ROOT"

say "copying the system (a few minutes)"
mkdir -p "$T" "$SQ"
mount "$ROOT" "$T"
mount -o loop,ro /cdrom/casper/filesystem.squashfs "$SQ"
cp -a "$SQ/." "$T/"
umount "$SQ"
mkdir -p "$T/boot/efi"
mount "$ESP" "$T/boot/efi"

say "configuring"
cat > "$T/etc/fstab" <<EOF
# <file system> <mount point> <type> <options> <dump> <pass>
UUID=$(blkid -s UUID -o value "$ROOT") / ext4 defaults 0 1
UUID=$(blkid -s UUID -o value "$ESP") /boot/efi vfat umask=0077 0 2
EOF
systemd-machine-id-setup --root="$T" >/dev/null
echo "$AI_HOSTNAME" > "$T/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\t%s\n\n::1\tip6-localhost ip6-loopback\nff02::1\tip6-allnodes\nff02::2\tip6-allrouters\n' \
  "$AI_HOSTNAME" > "$T/etc/hosts"
# The kernel the live system runs is the one its modules are for (Calamares' before_bootloader_kerncopy and LP#1829805).
KVER="$(uname -r)"
[ -d "$T/lib/modules/$KVER" ] || fail "the system has no modules for the live kernel $KVER"
cp /cdrom/casper/vmlinuz "$T/boot/vmlinuz-$KVER"
touch "$T/boot/initrd.img-$KVER"

for m in proc sys dev dev/pts run; do mkdir -p "$T/$m"; done
mount -t proc proc "$T/proc"
mount -t sysfs sys "$T/sys"
mount --bind /dev "$T/dev"
mount --bind /dev/pts "$T/dev/pts"
mount -t tmpfs tmpfs "$T/run"
[ ! -d /sys/firmware/efi/efivars ] || mount -t efivarfs efivarfs "$T/sys/firmware/efi/efivars"
mkdir -p "$T/run/systemd/resolve" "$T/cdrom"
[ ! -d /run/systemd/resolve ] || mount --bind /run/systemd/resolve "$T/run/systemd/resolve"
mount --bind /cdrom "$T/cdrom"
in_target() { chroot "$T" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 "$@"; }

# Locale, time zone, console keys.
printf 'LANG=%s\n' "$AI_LOCALE" > "$T/etc/default/locale"
sed -i "s/^# *\(${AI_LOCALE//./\\.}\)/\1/" "$T/etc/locale.gen" 2>/dev/null || true
in_target locale-gen >/dev/null || true
ln -sf "/usr/share/zoneinfo/$AI_TIMEZONE" "$T/etc/localtime"
echo "$AI_TIMEZONE" > "$T/etc/timezone"
[ ! -x /usr/libexec/fixconkeys-part1 ] || { /usr/libexec/fixconkeys-part1 "$T" && in_target /usr/libexec/fixconkeys-part2; } || true

# The account: Kubuntu's default groups (users.conf), the password from the build, autologin and passwordless sudo.
groups=""
for g in adm cdrom dip lpadmin plugdev sambashare sudo; do
  in_target getent group "$g" >/dev/null && groups+="${groups:+,}$g"
done
in_target useradd -m -s /bin/bash -c "$AI_FULLNAME" -G "$groups" "$AI_USER"
in_target usermod -p "$AI_PASSWORD_CRYPT" "$AI_USER"
mkdir -p "$T/etc/sddm.conf.d"
printf '[Autologin]\nUser=%s\nSession=plasma\nRelogin=false\n' "$AI_USER" > "$T/etc/sddm.conf.d/90-noctraos-autologin.conf"
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$AI_USER" > "$T/etc/sudoers.d/90-noctraos-firstboot"
chmod 440 "$T/etc/sudoers.d/90-noctraos-firstboot"

say "initramfs and boot loader"
in_target update-initramfs -c -k "$KVER" >/dev/null
# Signed GRUB and shim are already in the system (Calamares' apt step for them is a no-op on this ISO). Install the
# boot entry, and the same files at EFI/BOOT/BOOTX64.EFI so the disk also boots where the UEFI variables are empty.
in_target grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=ubuntu --uefi-secure-boot --recheck
in_target grub-install --target=x86_64-efi --efi-directory=/boot/efi --uefi-secure-boot --removable --no-nvram
in_target update-grub >/dev/null 2>&1
[ -f "$T/boot/efi/EFI/BOOT/BOOTX64.EFI" ] || fail "no removable boot loader on the ESP"
in_target dpkg --add-architecture i386

# apt sources as Calamares' automirror writes them (the live system only has the CD), then the live-only packages go.
codename="$(. "$T/etc/os-release" && echo "$VERSION_CODENAME")"
cat > "$T/etc/apt/sources.list.d/ubuntu.sources" <<EOF
Types: deb
URIs: http://archive.ubuntu.com/ubuntu
Suites: $codename $codename-updates $codename-backports
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://security.ubuntu.com/ubuntu/
Suites: $codename-security
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
rm -f "$T/etc/apt/sources.list" "$T/etc/apt/sources.list.d/cdrom.sources"
say "removing the installer packages"
# packages.conf's list; only the installed ones are named, since apt refuses a name or pattern that matches nothing.
mapfile -t live_pkgs < <(in_target dpkg-query -W -f='${Package} ${db:Status-Status}\n' | awk '$2 == "installed" {print $1}' \
  | grep -Ex 'live-.*|calamares|calamares-data|calamares-settings-kubuntu|calamares-settings-ubuntu-common(-data)?|libcalamaresui3\.3|cifs-utils|kubuntu-installer-prompt' || true)
[ "${#live_pkgs[@]}" = 0 ] || in_target apt-get purge -y -q "${live_pkgs[@]}" >/dev/null

# Nothing of this script stays behind: the unit, the script and the settings (a password hash) are the appliance ISO's.
rm -f "$T/etc/systemd/system/noctraos-autoinstall.service" "$T/etc/systemd/system/multi-user.target.wants/noctraos-autoinstall.service" \
  "$T/usr/local/sbin/noctraos-autoinstall" "$T/etc/noctraos/autoinstall.conf"
cp "$LOG" "$T/var/log/noctraos-autoinstall.log" 2>/dev/null || true

say "done: restarting into the installed system"
sync
umount -R "$T"
trap - ERR
systemctl reboot
