#!/usr/bin/env bash
# bake-shell.sh — puts the NoctraOS GNOME Shell pieces into the image, so the very first session has them.
# Sourced by build-noctraos-iso.sh.
#
#   bake_shell <squashfs-root> <provisioner-tree>
#
# GNOME Shell scans for extensions once, when it starts, and Wayland cannot restart it in place. The
# provisioner (module 09) runs inside the first session, so what it installs is only seen after the
# next sign-in: Super+Space and the Start panel were dead until the user signed out and in. With the
# files already in the image, the shell finds the extensions at its first start, and the two
# autostart setup scripts (which add them to `enabled-extensions`) switch them on live.
#
# This is the file-copy half of install/09_super_search.sh: keep the two lists in step. Module 09
# stays the owner (it copies only what differs, so on a baked image it changes nothing and still
# repairs an image that lacks a file). Nothing here needs apt, a network or a running session.

bake_shell() {
  local root="$1" repo="$2" uuid f
  local ext="$root/usr/share/gnome-shell/extensions" schemas="$root/usr/share/glib-2.0/schemas"
  for uuid in noctraos-search@noctraos.local noctraos-branding@noctraos.local noctraos-start@noctraos.local; do
    [ -d "$repo/extensions/$uuid" ] || { echo "bake_shell: extension missing in the snapshot: $uuid" >&2; return 1; }
    install -d -m 755 "$ext/$uuid"
    for f in "$repo/extensions/$uuid"/*; do install -m 644 "$f" "$ext/$uuid/"; done
  done

  install -d -m 755 "$root/usr/local/share/noctraos-search" "$root/usr/local/share/noctraos/help" "$root/usr/local/bin"
  for f in "$repo"/search/*.py; do install -m 644 "$f" "$root/usr/local/share/noctraos-search/"; done
  install -m 755 "$repo/bin/noctraos-search" "$repo/bin/noctraos-weather" "$root/usr/local/bin/"
  install -m 644 "$repo/help/index.html" "$root/usr/local/share/noctraos/help/index.html"
  install -m 755 "$repo/branding/setup-branding.py" "$root/usr/local/share/noctraos/setup-branding.py"

  install -d -m 755 "$schemas"
  install -m 644 "$repo"/configs/gsettings/org.gnome.shell.extensions.noctraos-search.gschema.xml \
    "$repo"/configs/gsettings/org.gnome.shell.extensions.noctraos-start.gschema.xml \
    "$repo"/configs/gsettings/90_noctraos-updates.gschema.override "$schemas/"
  # The image's own compiler when we can chroot into it (the build runs as root and the builder
  # container has no glib tools); the host's otherwise (tests). It only reads XML and overrides.
  if [ "$(id -u)" -eq 0 ] && [ -x "$root/usr/bin/glib-compile-schemas" ]; then
    chroot "$root" /usr/bin/glib-compile-schemas /usr/share/glib-2.0/schemas
  else
    glib-compile-schemas "$schemas"
  fi || { echo "bake_shell: glib-compile-schemas failed" >&2; return 1; }

  # Both setups are once per account and idempotent; module 09 installs the same two entries later.
  install -d -m 755 "$root/etc/xdg/autostart"
  install -m 644 "$repo/configs/autostart/noctraos-search-setup.desktop" \
    "$repo/configs/autostart/noctraos-branding.desktop" "$root/etc/xdg/autostart/"
}
