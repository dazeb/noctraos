#!/usr/bin/env bash
# Module 10: boot chain — Plymouth splash and GRUB menu theme.
# The ISO already ships both (iso/boot-theme.sh); this brings an installation that
# came from somewhere else (stock Zorin + install.sh) to the same state.
# Everything here is best-effort: a failed splash must never fail an install.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

BOOT_SRC="$REPO_ROOT/assets/boot"
PLY_DIR="/usr/share/plymouth/themes/noctraos"
GRUB_DIR="/usr/share/grub/themes/noctraos"

sync_dir() { # <src> <dst>: replace dst when it differs, so reruns change nothing
  if ! diff -qr "$1" "$2" >/dev/null 2>&1; then
    sudo rm -rf "$2"
    sudo mkdir -p "$(dirname "$2")"
    sudo cp -r "$1" "$2"
    sudo chmod -R a+rX "$2"
    return 0
  fi
  return 1
}

# --- Plymouth -----------------------------------------------------------------
if [ -d /usr/share/plymouth/themes ] && have update-alternatives; then
  ply_changed=0
  sync_dir "$BOOT_SRC/plymouth/noctraos" "$PLY_DIR" && ply_changed=1
  # Priority above Zorin's 200 so the alternative resolves to ours in auto mode;
  # --install is a no-op when the same entry is already registered.
  sudo update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth \
    "$PLY_DIR/noctraos.plymouth" 300 \
    --slave /usr/share/plymouth/themes/default.grub default.plymouth.grub "$PLY_DIR/noctraos.grub" \
    || warn "Could not register the NoctraOS splash"
  # The splash is baked into the initramfs, so rebuild it unless it already has ours.
  initrd="/boot/initrd.img-$(uname -r)"
  if [ -f "$initrd" ] && have update-initramfs; then
    if [ "$ply_changed" -eq 1 ] || ! sudo lsinitramfs "$initrd" 2>/dev/null | grep 'themes/noctraos/' >/dev/null; then
      log "Rebuilding the initramfs with the NoctraOS splash"
      sudo update-initramfs -u -k "$(uname -r)" || warn "update-initramfs failed — splash unchanged until the next kernel update"
    fi
  fi
else
  warn "Plymouth not installed — splash left as is"
fi

# --- GRUB ---------------------------------------------------------------------
if [ -f /etc/default/grub ] && have update-grub; then
  grub_changed=0
  sync_dir "$BOOT_SRC/grub/noctraos" "$GRUB_DIR" && grub_changed=1
  if ! grep -qx "GRUB_THEME=$GRUB_DIR/theme.txt" /etc/default/grub; then
    if grep -q '^GRUB_THEME=' /etc/default/grub; then
      sudo sed -i "s|^GRUB_THEME=.*|GRUB_THEME=$GRUB_DIR/theme.txt|" /etc/default/grub
    else
      echo "GRUB_THEME=$GRUB_DIR/theme.txt" | sudo tee -a /etc/default/grub >/dev/null
    fi
    grub_changed=1
  fi
  # Menu entry titles: "NoctraOS" instead of the base distribution's name.
  if ! grep -qx 'GRUB_DISTRIBUTOR=NoctraOS' /etc/default/grub; then
    if grep -q '^GRUB_DISTRIBUTOR=' /etc/default/grub; then
      sudo sed -i 's|^GRUB_DISTRIBUTOR=.*|GRUB_DISTRIBUTOR=NoctraOS|' /etc/default/grub
    else
      echo 'GRUB_DISTRIBUTOR=NoctraOS' | sudo tee -a /etc/default/grub >/dev/null
    fi
    grub_changed=1
  fi
  if [ "$grub_changed" -eq 1 ]; then
    sudo update-grub || warn "update-grub failed — GRUB menu unchanged"
  fi
else
  warn "GRUB not managed here — menu theme skipped"
fi
