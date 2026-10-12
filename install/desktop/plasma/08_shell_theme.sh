#!/usr/bin/env bash
# desktops: plasma
# Plasma module 08: the NoctraOS look outside the panel — the login screen (SDDM), the splash after login, the lock screen,
# the Global Theme and wallpaper packages in System Settings, and "About this System". The system-wide part is
# configs/plasma/install-look.sh, which the kubuntu ISO also bakes in; this module adds the per-account About page.
# Every step is warn-not-die: a settings drift must never abort the install.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_plasma; then
  warn "NOT APPLIED on this desktop: login screen, splash, lock screen and Global Theme"
  exit 0
fi

log "Installing the NoctraOS login screen, splash, lock screen and Global Theme..."
if sudo bash "$REPO_ROOT/configs/plasma/install-look.sh" /; then
  log "OK: login screen and splash appear at the next login; the Global Theme is listed in System Settings"
else
  warn "The NoctraOS look was not fully installed; re-run: install.sh --only 08_shell_theme.sh"
fi

# About this System: install-look.sh writes the account template; existing accounts get the same file (it holds only our
# name, logo, version and site, so it is refreshed on every run to keep the version current).
ABOUT_SRC=/etc/skel/.config/kcm-about-distrorc
ABOUT_DST="$TARGET_HOME/.config/kcm-about-distrorc"
if [ -f "$ABOUT_SRC" ] && grep -Fqx "# Written by NoctraOS (configs/plasma/install-look.sh)." "$ABOUT_SRC"; then
  if [ ! -e "$ABOUT_DST" ] || grep -Fqx "# Written by NoctraOS (configs/plasma/install-look.sh)." "$ABOUT_DST"; then
    cmp -s "$ABOUT_SRC" "$ABOUT_DST" 2>/dev/null || as_user install -D -m 644 "$ABOUT_SRC" "$ABOUT_DST" \
      || warn "Could not write $ABOUT_DST"
    log "OK: About this System shows NoctraOS"
  else
    warn "Kept your own $ABOUT_DST (About this System)"
  fi
fi
sudo kbuildsycoca6 >/dev/null 2>&1 || as_user kbuildsycoca6 >/dev/null 2>&1 || true
