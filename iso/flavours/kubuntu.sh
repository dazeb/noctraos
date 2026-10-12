#!/usr/bin/env bash
# kubuntu.sh — remaster a Kubuntu 26.04 live ISO into NoctraOS (flavour: kubuntu).
#
# The Kubuntu counterpart of the Zorin remaster (iso/build-noctraos-iso.sh). It shares only flavour-neutral helpers
# (iso/bake-guest-tools.sh); everything that depends on the base lives here. What the real kubuntu-26.04.1 ISO looks like
# (read from the ISO, 2026-10-11) and why this script differs from the Zorin one:
#   - BIOS and UEFI both boot through GRUB (no isolinux); the kernel and initrd are casper/vmlinuz and casper/initrd
#     (plain cpio, no .zstd name); there is one casper/filesystem.squashfs and no filesystem.size.
#   - The installer is Calamares (not Ubiquity): branding is /etc/calamares/branding/<name>, settings in
#     /etc/calamares/settings.conf. Calamares has no unattended mode, so the appliance build (NOCTRAOS_UNATTENDED=1, only
#     ever used to make the VM disks, never published) installs with iso/flavours/kubuntu-autoinstall.sh instead.
#   - The display manager is SDDM and the session is Plasma (Wayland). Autologin of the live user is the live image's own.
#
# What it does: extract the ISO tree, unpack the squashfs (owners kept), bake in the provisioner snapshot, the flavour file
# (/etc/noctraos/flavour = kubuntu), the first-boot runner and its autostart, qemu-guest-agent, the NoctraOS names (os-release,
# Calamares, GRUB entries), the GRUB menu theme and the installed system's Plymouth/GRUB theme, the installer's artwork and
# slideshow (assets/boot/calamares), and the Plasma look the first login shows (configs/plasma/install-look.sh: login screen,
# splash, lock screen, Global Theme, wallpapers); repack with the original compressor and write a new ISO that replays the
# original BIOS+UEFI boot equipment.
#
# Not done yet (the Plasma desktop is phase 4, the live splash is not planned): the panel layout before provisioning,
# Super+Space, the live session's Plymouth splash (stays Kubuntu's).
#
# Usage:  sudo iso/flavours/kubuntu.sh <kubuntu-live.iso> [out.iso]
# Needs:  xorriso, squashfs-tools, git, update-alternatives, chroot, python3, ~25 GiB scratch (set WORK_BASE).
# Knobs:  WORK_BASE (scratch), REPO_URL, NOCTRAOS_BRANCH (provisioner branch baked in and fetched at first boot).
#         NOCTRAOS_UNATTENDED=1 with NOCTRAOS_USER, NOCTRAOS_PASSWORD, NOCTRAOS_HOSTNAME: the appliance ISO (see kubuntu_appliance).
# Sourcing this file only defines the functions (tests/test_kubuntu_iso.py).

KB_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ISO_DIR="$(cd "$KB_HERE/.." && pwd)"
KB_REPO_ROOT="$(cd "$KB_ISO_DIR/.." && pwd)"
KB_BOOT_ASSETS="$KB_REPO_ROOT/assets/boot"

# A line that must change exactly once: a base image that changed shape fails the build instead of shipping half renamed.
kb_replace() { # kb_replace <file> <sed expression> <what>
  local file="$1" expr="$2" what="$3" before
  [ -f "$file" ] || { echo "kubuntu: $what: $file not found (base image differs from what this expects)" >&2; return 1; }
  before="$(md5sum "$file")"
  sed -i -e "$expr" "$file"
  [ "$(md5sum "$file")" != "$before" ] || { echo "kubuntu: $what: nothing to change in $file (base image differs)" >&2; return 1; }
}

# The layout this script was written against; anything else is refused, never guessed at.
kubuntu_check_layout() { # kubuntu_check_layout <iso-tree>
  local tree="$1" f
  for f in casper/filesystem.squashfs casper/initrd casper/vmlinuz boot/grub/grub.cfg .disk/info md5sum.txt; do
    [ -f "$tree/$f" ] || { echo "kubuntu: unexpected layout: $f not found (is this a Kubuntu desktop live ISO?)" >&2; return 1; }
  done
  grep -q '^Kubuntu' "$tree/.disk/info" || { echo "kubuntu: .disk/info does not say Kubuntu: $(cat "$tree/.disk/info")" >&2; return 1; }
  grep -q 'menuentry "Try or Install Kubuntu"' "$tree/boot/grub/grub.cfg" \
    || { echo "kubuntu: boot/grub/grub.cfg has no 'Try or Install Kubuntu' entry (layout changed)" >&2; return 1; }
  [ -d "$tree/boot/grub/x86_64-efi" ] && [ -d "$tree/boot/grub/i386-pc" ] \
    || { echo "kubuntu: GRUB modules for both UEFI and BIOS are expected under boot/grub" >&2; return 1; }
}

# Boot menu: NoctraOS names and the NoctraOS GRUB theme, for the entries both firmware types share.
kubuntu_theme_grub() { # kubuntu_theme_grub <iso-tree>
  local tree="$1" cfg="$1/boot/grub/grub.cfg" theme_dir="$1/boot/grub/themes/noctraos" f fonts=""
  rm -rf "$theme_dir"
  mkdir -p "$theme_dir"
  cp "$KB_BOOT_ASSETS"/grub/noctraos/* "$theme_dir/"
  kb_replace "$cfg" 's/Kubuntu/NoctraOS/g' "GRUB menu names" || return 1
  [ ! -f "$tree/boot/grub/loopback.cfg" ] || kb_replace "$tree/boot/grub/loopback.cfg" 's/Kubuntu/NoctraOS/g' "loopback menu names" || return 1
  for f in "$theme_dir"/*.pf2; do
    fonts+="loadfont /boot/grub/themes/noctraos/$(basename "$f")\n"
  done
  # The stock file has `loadfont unicode` and plain colours; the theme needs the graphical terminal and the PNG reader.
  kb_replace "$cfg" "s|^loadfont unicode\$|loadfont unicode\ninsmod all_video\ninsmod gfxterm\ninsmod png\nset gfxmode=auto\nterminal_output gfxterm\n${fonts}set theme=/boot/grub/themes/noctraos/theme.txt|" \
    "GRUB theme hook" || return 1
}

# Names a person sees: About, the console banner, the installer, the live host name.
kubuntu_rebrand() { # kubuntu_rebrand <squashfs-root> <version>
  local root="$1" version="$2" f
  [ -n "$version" ] || { echo "kubuntu_rebrand: no version" >&2; return 1; }
  # /etc/os-release is a symlink to usr/lib/os-release. ID, ID_LIKE, VERSION_ID and the codename stay (apt, Calamares and the
  # provisioner's OS check key on them); what changes is what the About page and the banner print.
  f="$root/usr/lib/os-release"
  kb_replace "$f" "s|^PRETTY_NAME=.*|PRETTY_NAME=\"NoctraOS $version\"|" "os-release PRETTY_NAME" || return 1
  kb_replace "$f" 's|^NAME=.*|NAME="NoctraOS"|' "os-release NAME" || return 1
  kb_replace "$f" "s|^VERSION=.*|VERSION=\"$version\"|" "os-release VERSION" || return 1
  kb_replace "$f" 's|^HOME_URL=.*|HOME_URL="https://noctraos.dev/"|' "os-release HOME_URL" || return 1
  kb_replace "$f" 's|^SUPPORT_URL=.*|SUPPORT_URL="https://github.com/dazeb/noctraos/issues"|' "os-release SUPPORT_URL" || return 1
  kb_replace "$f" 's|^BUG_REPORT_URL=.*|BUG_REPORT_URL="https://github.com/dazeb/noctraos/issues"|' "os-release BUG_REPORT_URL" || return 1
  kb_replace "$f" 's|^PRIVACY_POLICY_URL=.*|PRIVACY_POLICY_URL="https://noctraos.dev/"|' "os-release PRIVACY_POLICY_URL" || return 1
  kb_replace "$f" 's|^LOGO=.*|LOGO=noctraos-logo|' "os-release LOGO" || return 1
  kb_replace "$root/etc/lsb-release" "s|^DISTRIB_DESCRIPTION=.*|DISTRIB_DESCRIPTION=\"NoctraOS $version\"|" "lsb-release" || return 1
  kb_replace "$root/etc/issue" "s|Ubuntu [0-9.]* LTS|NoctraOS $version|" "/etc/issue" || return 1
  kb_replace "$root/etc/issue.net" "s|Ubuntu [0-9.]* LTS|NoctraOS $version|" "/etc/issue.net" || return 1
  # The live session's host and user name are the base's: casper ignores /etc/casper.conf unless FLAVOUR is set, and a
  # Kubuntu live ISO sets none. Left alone on purpose.
  install -D -m 644 "$KB_REPO_ROOT/assets/icons/noctraos-logo.svg" "$root/usr/share/icons/hicolor/scalable/apps/noctraos-logo.svg"
  install -D -m 644 "$KB_REPO_ROOT/assets/icons/noctraos-logo.svg" "$root/usr/share/pixmaps/noctraos-logo.svg"
  chroot "$root" gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
}

# Calamares: a branding of our own (Kubuntu's branding.desc with our names, our pictures and slideshow), selected in
# settings.conf. The pictures are rendered by scripts/render-kubuntu-branding.py.
KB_CALAMARES_ART="$KB_BOOT_ASSETS/calamares"
kubuntu_calamares() { # kubuntu_calamares <squashfs-root> <version>
  local root="$1" version="$2" src="$1/etc/calamares/branding/kubuntu" dst="$1/etc/calamares/branding/noctraos" f slides=""
  [ -f "$src/branding.desc" ] || { echo "kubuntu: Calamares branding 'kubuntu' not found (installer changed?)" >&2; return 1; }
  rm -rf "$dst"
  mkdir -p "$dst"
  cp "$src/branding.desc" "$dst/branding.desc"
  for f in logo.png icon.png welcome.png; do
    install -m 644 "$KB_CALAMARES_ART/$f" "$dst/$f"
  done
  install -m 644 "$KB_CALAMARES_ART/welcome.png" "$dst/welcome-oem.png"
  for f in "$KB_CALAMARES_ART"/slide-*.png; do
    install -m 644 "$f" "$dst/$(basename "$f")"
    # The same slide element Kubuntu's own show.qml uses, one per picture.
    slides+="    Slide {
        Image {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: - parent.y / 3.6
            height: parent.masterHeight * 0.95
            width: parent.masterWidth * 0.95
            fillMode: Image.PreserveAspectFit
            smooth: true
            source: \"$(basename "$f")\"
        }
    }
"
  done
  [ -n "$slides" ] || { echo "kubuntu: no slides in $KB_CALAMARES_ART" >&2; return 1; }
  f="$dst/branding.desc"
  kb_replace "$f" 's|^componentName:.*|componentName: noctraos|' "branding componentName" || return 1
  kb_replace "$f" "s#^\\( *\\)\\(productName\\|shortProductName\\|versionedName\\|bootloaderEntryName\\):\\( *\\)Kubuntu\$#\\1\\2:\\3NoctraOS#" "branding names" || return 1
  kb_replace "$f" "s|^\\( *\\)shortVersionedName:\\( *\\)Kubuntu .*|\\1shortVersionedName:\\2NoctraOS $version|" "branding versioned name" || return 1
  kb_replace "$f" "s|^\\( *\\)version:\\( *\\)[0-9].*|\\1version:\\2$version|" "branding version" || return 1
  kb_replace "$f" 's|^\( *\)productUrl:.*|\1productUrl:          https://noctraos.dev/|' "branding productUrl" || return 1
  kb_replace "$f" 's|^\( *\)supportUrl:.*|\1supportUrl:          https://github.com/dazeb/noctraos/issues|' "branding supportUrl" || return 1
  kb_replace "$f" 's|^\( *\)SidebarBackground:.*|\1SidebarBackground:    "#1a1a1a"|' "branding sidebar" || return 1
  kb_replace "$f" 's|^\( *\)SidebarTextCurrent:.*|\1SidebarTextCurrent:   "#e68e0d"|' "branding sidebar text" || return 1
  {
    printf '%s\n' 'import QtQuick 2.0;' 'import calamares.slideshow 1.0;' '' 'Presentation' '{' '    id: presentation' '' \
      '    Timer {' '        interval: 12000' '        running: true' '        repeat: true' \
      '        onTriggered: presentation.goToNextSlide()' '    }'
    printf '%s' "$slides"
    printf '}\n'
  } > "$dst/show.qml"
  kb_replace "$root/etc/calamares/settings.conf" 's|^branding: kubuntu$|branding: noctraos|' "Calamares settings branding" || return 1
}

# The installed system: Plymouth and GRUB menu themes (the installer rebuilds the target's initramfs from this theme).
kubuntu_boot_theme_squashfs() { # kubuntu_boot_theme_squashfs <squashfs-root>
  local root="$1" ply="$1/usr/share/plymouth/themes/noctraos" grub="$1/usr/share/grub/themes/noctraos"
  rm -rf "$ply"
  mkdir -p "$(dirname "$ply")"
  cp -r "$KB_BOOT_ASSETS/plymouth/noctraos" "$ply"
  update-alternatives --root "$root" --install /usr/share/plymouth/themes/default.plymouth default.plymouth \
    /usr/share/plymouth/themes/noctraos/noctraos.plymouth 300 \
    --slave /usr/share/plymouth/themes/default.grub default.plymouth.grub \
    /usr/share/plymouth/themes/noctraos/noctraos.grub
  update-alternatives --root "$root" --set default.plymouth /usr/share/plymouth/themes/noctraos/noctraos.plymouth
  rm -rf "$grub"
  mkdir -p "$grub"
  cp "$KB_BOOT_ASSETS"/grub/noctraos/* "$grub/"
  [ -f "$root/etc/default/grub" ] || { echo "kubuntu: /etc/default/grub not found" >&2; return 1; }
  grep -q '^GRUB_THEME=' "$root/etc/default/grub" || printf 'GRUB_THEME=\n' >> "$root/etc/default/grub"
  sed -i -e 's|^GRUB_THEME=.*|GRUB_THEME=/usr/share/grub/themes/noctraos/theme.txt|' \
         -e 's|^GRUB_DISTRIBUTOR=.*|GRUB_DISTRIBUTOR=NoctraOS|' "$root/etc/default/grub"
}

# The Plasma look of the installed system (login screen, splash, lock screen, Global Theme, wallpapers, About), so the
# first login already shows it; the provisioner's Plasma module 08 runs the same script again.
kubuntu_look() { # kubuntu_look <squashfs-root>
  bash "$KB_REPO_ROOT/configs/plasma/install-look.sh" "$1"
}

# First-boot provisioning: the runner (shared text, iso/firstboot-runner.sh), its autostart, the flavour file and the snapshot.
kubuntu_firstboot() { # kubuntu_firstboot <squashfs-root> <branch>
  local root="$1" branch="$2" runner="$1/usr/local/sbin/noctraos-firstboot"
  mkdir -p "$root/usr/local/sbin" "$root/etc/skel/.config/autostart" "$root/etc/noctraos"
  sed "s|__NOCTRAOS_BRANCH__|$branch|" "$KB_ISO_DIR/firstboot-runner.sh" > "$runner"
  chmod 755 "$runner"
  # Not in the live session (the installer ISO boots with boot=casper): only an installed system provisions itself.
  cat > "$root/etc/skel/.config/autostart/noctraos-setup.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=noctraos Setup
Comment=One-time setup of your AI developer workstation
Exec=sh -c 'grep -qw boot=casper /proc/cmdline || exec /usr/local/sbin/noctraos-firstboot'
Terminal=true
Categories=System;
NoDisplay=false
EOF
  # The flavour picks the update channel and the desktop modules: written once, here, never guessed later.
  printf 'kubuntu\n' > "$root/etc/noctraos/flavour"
  chmod 644 "$root/etc/noctraos/flavour"
}

# The appliance ISO (NOCTRAOS_UNATTENDED=1): boots straight into kubuntu-autoinstall.sh, which erases the first disk and
# installs with autologin and passwordless sudo for <user>. Only for building the VM disks (iso/build-release.sh); it carries
# a password hash, so it is never published, and build-local.sh refuses a release ISO that has any of this.
kubuntu_appliance() { # kubuntu_appliance <squashfs-root> <iso-tree> <user> <password> [hostname]
  local root="$1" tree="$2" user="$3" password="$4" hostname="${5:-noctraos}" cfg="$2/boot/grub/grub.cfg" crypt entry
  [ -n "$user" ] && [ -n "$password" ] || { echo "kubuntu: the appliance build needs NOCTRAOS_USER and NOCTRAOS_PASSWORD" >&2; return 1; }
  crypt="$(openssl passwd -6 "$password")"
  install -D -m 755 "$KB_HERE/kubuntu-autoinstall.sh" "$root/usr/local/sbin/noctraos-autoinstall"
  mkdir -p "$root/etc/noctraos" "$root/etc/systemd/system/multi-user.target.wants"
  printf 'AI_USER=%q\nAI_PASSWORD_CRYPT=%q\nAI_HOSTNAME=%q\nAI_FULLNAME=NoctraOS\nAI_LOCALE=en_US.UTF-8\nAI_TIMEZONE=Etc/UTC\n' \
    "$user" "$crypt" "$hostname" > "$root/etc/noctraos/autoinstall.conf"
  chmod 600 "$root/etc/noctraos/autoinstall.conf"
  printf '%s\n' '[Unit]' 'Description=NoctraOS unattended install (appliance build only)' \
    'ConditionKernelCommandLine=noctraos.autoinstall' 'After=local-fs.target systemd-udev-settle.service' '' \
    '[Service]' 'Type=oneshot' 'ExecStart=/usr/local/sbin/noctraos-autoinstall' 'StandardOutput=journal+console' '' \
    '[Install]' 'WantedBy=multi-user.target' > "$root/etc/systemd/system/noctraos-autoinstall.service"
  ln -sf ../noctraos-autoinstall.service "$root/etc/systemd/system/multi-user.target.wants/noctraos-autoinstall.service"
  # The default entry, first in the menu with a short timeout. multi-user.target: no live desktop, the install has the machine.
  # noprompt: casper does not wait for "remove the installation medium" at the reboot.
  entry='menuentry "Install NoctraOS (unattended, erases the disk)" {
    set gfxpayload=keep
    linux  /casper/vmlinuz noctraos.autoinstall noprompt systemd.unit=multi-user.target --- quiet
    initrd /casper/initrd
}'
  kb_replace "$cfg" 's/^set timeout=[0-9]*/set timeout=3/' "GRUB timeout" || return 1
  awk -v e="$entry" '!d && /^menuentry / { print e; print ""; d=1 } { print }' "$cfg" > "$cfg.new" && mv "$cfg.new" "$cfg"
  grep -q 'noctraos.autoinstall' "$cfg" || { echo "kubuntu: the unattended boot entry was not added" >&2; return 1; }
}

kubuntu_main() {
  local src_iso="${1:?usage: kubuntu.sh <kubuntu-live.iso> [out.iso]}" out_iso="${2:-noctraos-kubuntu-amd64.iso}"
  local repo="${REPO_URL:-https://github.com/dazeb/noctraos.git}" branch="${NOCTRAOS_BRANCH:-main}" work_base="${WORK_BASE:-/var/tmp}"
  local work iso_tree sq_root comp sq_info version helper_gid helper_owner
  set -Eeuo pipefail
  step() { printf '\n\033[1;36m[noctraos-iso kubuntu]\033[0m %s\n' "$*"; }
  need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }; }
  need xorriso; need unsquashfs; need mksquashfs; need git; need python3; need update-alternatives; need chroot
  [ "${NOCTRAOS_UNATTENDED:-0}" != 1 ] || need openssl
  # shellcheck source=iso/bake-guest-tools.sh
  source "$KB_ISO_DIR/bake-guest-tools.sh"
  [ "$(id -u)" -eq 0 ] || { echo "run as root (squashfs device nodes need it)" >&2; exit 1; }
  [ -f "$src_iso" ] || { echo "no such ISO: $src_iso" >&2; exit 1; }
  work="$(mktemp -d "$work_base/noctraos-iso-build.XXXXXXXX")"
  iso_tree="$work/iso"; sq_root="$work/squashfs-root"
  # $work is local to this function, so the trap must expand it now, not when it runs after the function returns
  # shellcheck disable=SC2064
  trap "echo \"work dir kept for inspection: $work (remove with rm -rf)\"" EXIT
  mkdir -p "$iso_tree" "$sq_root"

  step "1/7 extracting ISO tree"
  xorriso -osirrox on -indev "$src_iso" -extract / "$iso_tree" >/dev/null 2>&1
  kubuntu_check_layout "$iso_tree"

  step "2/7 reading squashfs parameters"
  sq_info="$(unsquashfs -s "$iso_tree/casper/filesystem.squashfs")"
  comp="$(awk '/Compression / && !/Parameters/ {print $2; exit}' <<<"$sq_info")"
  [ -n "$comp" ] || { echo "could not detect squashfs compressor" >&2; exit 1; }
  echo "original compressor: $comp"

  step "3/7 unpacking squashfs (this takes a few minutes)"
  unsquashfs -no-progress -d "$sq_root" "$iso_tree/casper/filesystem.squashfs" >/dev/null
  # The original squashfs is not needed again (the new one replaces it) and the scratch disk is tight: it is ~4 GiB.
  rm -f "$iso_tree/casper/filesystem.squashfs"
  # Owners must survive the round trip (see AGENTS.md, "Never repack the system with mksquashfs -all-root").
  helper_gid="$(stat -c %g "$sq_root/usr/lib/dbus-1.0/dbus-daemon-launch-helper" 2>/dev/null || echo 0)"
  [ "$helper_gid" != 0 ] || {
    echo "unpacking lost file ownership (dbus-daemon-launch-helper is group root): build as real root with CAP_CHOWN" >&2; exit 1; }

  step "4/7 injecting the provisioner and rebranding"
  rm -rf "$sq_root/opt/noctraos"
  git clone --depth 1 --branch "$branch" "$repo" "$sq_root/opt/noctraos" >/dev/null 2>&1
  git -C "$sq_root/opt/noctraos" rev-parse HEAD > "$sq_root/opt/noctraos/.noctraos-commit"
  rm -rf "$sq_root/opt/noctraos/.git"
  version="$(tr -d '[:space:]' < "$sq_root/opt/noctraos/VERSION" 2>/dev/null || true)"
  [ -n "$version" ] || { echo "ERROR: VERSION file missing from the provisioner snapshot" >&2; exit 1; }
  step "release version: $version"
  mkdir -p "$sq_root/etc"
  printf 'NOCTRAOS_VERSION=%s\nNOCTRAOS_BASE="Kubuntu 26.04.1 (Ubuntu 26.04)"\n' "$version" > "$sq_root/etc/noctraos-release"
  kubuntu_firstboot "$sq_root" "$branch"
  kubuntu_rebrand "$sq_root" "$version"
  kubuntu_calamares "$sq_root" "$version"
  kubuntu_boot_theme_squashfs "$sq_root"
  kubuntu_look "$sq_root"
  bake_guest_tools "$sq_root"
  kubuntu_theme_grub "$iso_tree"
  if [ "${NOCTRAOS_UNATTENDED:-0}" = 1 ]; then
    step "appliance build: unattended install for ${NOCTRAOS_USER:-?} (never publish this ISO)"
    kubuntu_appliance "$sq_root" "$iso_tree" "${NOCTRAOS_USER:-}" "${NOCTRAOS_PASSWORD:-}" "${NOCTRAOS_HOSTNAME:-noctraos}"
  fi
  echo "NoctraOS $version 64bit (Kubuntu base)" > "$iso_tree/.disk/info"
  chown -R root:root "$sq_root/opt/noctraos" "$sq_root/usr/local/sbin" "$sq_root/etc/noctraos" \
    "$sq_root/etc/skel/.config/autostart"

  step "5/7 repacking squashfs ($comp — this is the long step)"
  mksquashfs "$sq_root" "$work/filesystem.squashfs" -comp "$comp" -noappend -no-progress -info >/dev/null
  helper_owner="$(unsquashfs -lln "$work/filesystem.squashfs" usr/lib/dbus-1.0/dbus-daemon-launch-helper 2>/dev/null \
    | awk '/dbus-daemon-launch-helper/ {print $2; exit}')"
  [ -n "$helper_owner" ] && [ "$helper_owner" != "0/0" ] || {
    echo "the repacked squashfs lost file ownership (launch helper owner: ${helper_owner:-missing})" >&2; exit 1; }

  step "6/7 refreshing ISO metadata"
  mv "$work/filesystem.squashfs" "$iso_tree/casper/filesystem.squashfs"
  ( cd "$iso_tree" && find . -type f ! -name 'md5sum.txt*' ! -name boot.cat -print0 | xargs -0 md5sum > ../md5sum.new \
      && mv ../md5sum.new md5sum.txt )

  rm -rf "$sq_root"   # ~12 GiB that the ISO write does not need
  step "7/7 writing $out_iso (boot equipment replayed from source ISO)"
  rm -f "$out_iso"
  xorriso -indev "$src_iso" \
    -outdev "$out_iso" \
    -boot_image any replay \
    -volid "NOCTRAOS_${version//./_}" \
    -map "$iso_tree/casper/filesystem.squashfs" /casper/filesystem.squashfs \
    -map "$iso_tree/md5sum.txt" /md5sum.txt \
    -map "$iso_tree/boot/grub/grub.cfg" /boot/grub/grub.cfg \
    -map "$iso_tree/boot/grub/loopback.cfg" /boot/grub/loopback.cfg \
    -map "$iso_tree/boot/grub/themes/noctraos" /boot/grub/themes/noctraos \
    -map "$iso_tree/.disk/info" /.disk/info \
    -padding 0
  step "done"
  ls -lh "$out_iso"
  sha256sum "$out_iso" | tee "$out_iso.sha256"
  echo "work dir: $work (safe to rm -rf)"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  kubuntu_main "$@"
fi
