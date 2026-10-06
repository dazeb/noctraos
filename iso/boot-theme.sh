#!/usr/bin/env bash
# boot-theme.sh — NoctraOS boot-chain staging for build-noctraos-iso.sh.
# Sourced; each function takes the extracted trees as arguments and edits them
# in place. Artwork lives in assets/boot (see generate-boot-assets.py).
#
#   boot_theme_iso_tree <iso-tree>    GRUB (UEFI) theme, isolinux (BIOS) theme and labels
#   boot_theme_initrd   <iso-tree>    live-boot Plymouth splash inside casper/initrd.zstd
#   boot_theme_squashfs <squashfs-root>
#                                     installed-system splash, GRUB theme and defaults,
#                                     dark live session, installer slideshow

BOOT_ASSETS="${BOOT_ASSETS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../assets/boot" && pwd)}"
BOOT_CONFIGS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../configs" && pwd)"

boot_theme_iso_tree() {
  local tree="$1" cfg="$1/boot/grub/grub.cfg" theme_dir="$1/boot/grub/themes/noctraos" f
  rm -rf "$theme_dir"
  mkdir -p "$theme_dir"
  cp "$BOOT_ASSETS"/grub/noctraos/* "$theme_dir/"

  # Stock cfg: `set theme=/boot/grub/themes/zorin/theme.txt` inside the loadfont branch.
  grep -q '^[[:space:]]*set theme=' "$cfg" || { echo "grub.cfg: no 'set theme=' line — layout changed" >&2; return 1; }
  local fonts=""
  for f in "$theme_dir"/*.pf2; do
    fonts+="	loadfont /boot/grub/themes/noctraos/$(basename "$f")\n"
  done
  sed -i -e "s|^\([[:space:]]*\)set theme=.*|${fonts}\1set theme=/boot/grub/themes/noctraos/theme.txt|" "$cfg"
  sed -i 's/Zorin OS/NoctraOS/g' "$cfg"

  # BIOS menu: splice our theme before the entries and rebrand the labels.
  local iso="$tree/isolinux"
  [ -f "$iso/isolinux.cfg" ] && [ -f "$iso/menuentries.cfg" ] \
    || { echo "isolinux: isolinux.cfg/menuentries.cfg missing — layout changed" >&2; return 1; }
  cp "$BOOT_ASSETS/isolinux/splash.png" "$iso/splash.png"
  sed -i '/^MENU BACKGROUND/d' "$iso/isolinux.cfg"
  awk -v theme="$BOOT_ASSETS/isolinux/theme.cfg" '
    /^INCLUDE menuentries.cfg/ { while ((getline line < theme) > 0) print line }
    { print }' "$iso/isolinux.cfg" > "$iso/isolinux.cfg.new" && mv "$iso/isolinux.cfg.new" "$iso/isolinux.cfg"
  sed -i 's/Zorin OS/NoctraOS/g' "$iso/menuentries.cfg"
}

boot_theme_initrd() {
  local initrd="$1/casper/initrd.zstd"
  [ -f "$initrd" ] || { echo "casper/initrd.zstd not found" >&2; return 1; }
  python3 "$(dirname "${BASH_SOURCE[0]}")/initrd-theme.py" "$initrd" "$BOOT_ASSETS/plymouth/noctraos" noctraos
}

boot_theme_squashfs() {
  local root="$1" ply="$1/usr/share/plymouth/themes/noctraos"
  # Plymouth: the installer rebuilds the target's initramfs from this theme.
  rm -rf "$ply"
  mkdir -p "$(dirname "$ply")"
  cp -r "$BOOT_ASSETS/plymouth/noctraos" "$ply"
  update-alternatives --root "$root" --install /usr/share/plymouth/themes/default.plymouth default.plymouth \
    /usr/share/plymouth/themes/noctraos/noctraos.plymouth 300 \
    --slave /usr/share/plymouth/themes/default.grub default.plymouth.grub \
    /usr/share/plymouth/themes/noctraos/noctraos.grub
  update-alternatives --root "$root" --set default.plymouth /usr/share/plymouth/themes/noctraos/noctraos.plymouth

  # GRUB menu on the installed system.
  local grub="$root/usr/share/grub/themes/noctraos"
  rm -rf "$grub"
  mkdir -p "$grub"
  cp "$BOOT_ASSETS"/grub/noctraos/* "$grub/"
  if [ -f "$root/etc/default/grub" ]; then
    sed -i -e 's|^GRUB_THEME=.*|GRUB_THEME=/usr/share/grub/themes/noctraos/theme.txt|' \
           -e 's|^GRUB_DISTRIBUTOR=.*|GRUB_DISTRIBUTOR=NoctraOS|' "$root/etc/default/grub"
  fi

  # Installer slideshow: one dark slide that teaches Super+Space, replacing Zorin's.
  local slides="$root/usr/share/ubiquity-slideshow/slides"
  if [ -f "$slides/welcome.html" ] && [ -f "$slides/link/base.css" ]; then
    install -m 644 "$BOOT_ASSETS/installer/welcome.html" "$slides/welcome.html"
    sed -i -e 's/#eaf0f6/#121212/g' -e 's/#123354/#bebebe/g' -e 's/#15a6f0/#e68e0d/g' \
           -e "s/font-family:'Inter', sans-serif;/font-family:'JetBrains Mono', monospace;/" "$slides/link/base.css"
    rm -f "$slides/screenshots/welcome.png"
    install -m 644 "$BOOT_ASSETS/installer/cd_in_tray.png" "$BOOT_ASSETS/installer/ubuntu_installed.png" \
      "$root/usr/share/ubiquity/pixmaps/"
  else
    echo "ubiquity slideshow not found — installer slide left as is" >&2
  fi

  # Live session and installer: dark grey instead of Zorin's light blue.
  # The wallpaper is the same file the provisioner installs later.
  local wall="$BOOT_ASSETS/../wallpapers/noctraos-ember-night-2160p.jpg"
  install -D -m 644 "$wall" "$root/usr/share/backgrounds/noctraos/ember-night.jpg"
  # Zorin sets its theme keys in `:zorin` session groups, which beat plain groups, so
  # the theme keys must be overridden in the same groups (this file sorts after 50_).
  cat > "$root/usr/share/glib-2.0/schemas/90_noctraos-live.gschema.override" <<'OVR'
[org.gnome.desktop.interface:zorin]
gtk-theme = 'ZorinGrey-Dark'
icon-theme = 'ZorinGrey-Dark'

[org.gnome.desktop.interface]
color-scheme = 'prefer-dark'

[org.gnome.shell.extensions.user-theme:zorin]
name = 'ZorinGrey-Dark'

[org.gnome.desktop.wm.preferences]
theme = 'ZorinGrey-Dark'

[org.gnome.desktop.background]
picture-uri = 'file:///usr/share/backgrounds/noctraos/ember-night.jpg'
picture-uri-dark = 'file:///usr/share/backgrounds/noctraos/ember-night.jpg'
OVR
  # The provisioner (module 09) installs this same file, but only after the first desktop login,
  # by which time Software Updater has already read first-run=true and shown "Zorin OS ...".
  install -m 644 "$BOOT_CONFIGS/gsettings/90_noctraos-updates.gschema.override" \
    "$root/usr/share/glib-2.0/schemas/90_noctraos-updates.gschema.override"
  chroot "$root" glib-compile-schemas --strict /usr/share/glib-2.0/schemas
}
