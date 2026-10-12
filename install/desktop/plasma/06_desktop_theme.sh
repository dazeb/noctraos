#!/usr/bin/env bash
# desktops: plasma
# Plasma module 06: the NoctraOS look and layout on KDE Plasma — colour scheme, Konsole profile, wallpapers, the Agents menu
# section and launchers, and the panel layout (applied from the session by an autostart entry).
# Every step is warn-not-die: a settings drift must never abort the install.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_plasma; then
  warn "NOT APPLIED on this desktop: Plasma colour scheme, Konsole profile, wallpaper and panel layout"
  exit 0
fi

PLASMA_SHARE=/usr/local/share/noctraos/plasma
USER_SHARE="$TARGET_HOME/.local/share"
kwrite() { as_user kwriteconfig6 "$@" || warn "kwriteconfig6 failed: $*"; }

log "Installing the NoctraOS colour scheme and the Konsole profile..."
as_user mkdir -p "$USER_SHARE/color-schemes" "$USER_SHARE/konsole"
as_user install -m 644 "$REPO_ROOT/configs/plasma/NoctraOSDark.colors" "$USER_SHARE/color-schemes/NoctraOSDark.colors"
as_user install -m 644 "$REPO_ROOT/configs/plasma/konsole/NoctraOS.colorscheme" "$USER_SHARE/konsole/NoctraOS.colorscheme"
as_user install -m 644 "$REPO_ROOT/configs/plasma/konsole/NoctraOS.profile" "$USER_SHARE/konsole/NoctraOS.profile"
kwrite --file kdeglobals --group General --key ColorScheme NoctraOSDark
kwrite --file konsolerc --group "Desktop Entry" --key DefaultProfile NoctraOS.profile
# Apply to a running session too; there is nothing to do (and no error) when nobody is logged in.
as_user plasma-apply-colorscheme NoctraOSDark >/dev/null 2>&1 || true

log "Installing AI agent launchers and the 'Agents' menu section..."
sudo mkdir -p /usr/local/share/applications /usr/share/desktop-directories \
              /etc/xdg/menus/plasma-applications-merged /usr/local/share/icons/hicolor/scalable/apps /usr/local/bin
sudo install -m 755 "$REPO_ROOT/bin/noctraos-agent" /usr/local/bin/noctraos-agent
sudo install -m 755 "$REPO_ROOT/bin/noctraos-hermes" /usr/local/bin/noctraos-hermes
sudo install -D -m 644 "$REPO_ROOT/configs/hermes/onboarding.md" /usr/local/share/noctraos/hermes/onboarding.md
install_launchers "$REPO_ROOT"
sudo install -m 644 "$REPO_ROOT/configs/applications/noctraos-agents.directory" /usr/share/desktop-directories/
sudo install -m 644 "$REPO_ROOT/configs/applications/noctraos-local-llm.directory" /usr/share/desktop-directories/
sudo install -m 644 "$REPO_ROOT/configs/xdg/noctraos-agents.menu" /etc/xdg/menus/plasma-applications-merged/
for i in "$REPO_ROOT"/assets/icons/hermes/hicolor/*/apps/hermes.png; do
  [ -f "$i" ] || continue
  size="$(basename "$(dirname "$(dirname "$i")")")"
  cmp -s "$i" "/usr/local/share/icons/hicolor/$size/apps/hermes.png" 2>/dev/null \
    || sudo install -D -m 644 "$i" "/usr/local/share/icons/hicolor/$size/apps/hermes.png"
done
sudo kbuildsycoca6 >/dev/null 2>&1 || as_user kbuildsycoca6 >/dev/null 2>&1 || true
log "OK: Agents section (Hermes preinstalled by module 11, the other agents install on first use)"

log "Installing the wallpaper set..."
WALLPAPER_DIR="/usr/local/share/backgrounds/noctraos"
sudo mkdir -p "$WALLPAPER_DIR"
for wp in "$REPO_ROOT"/assets/wallpapers/*.jpg; do
  [ -f "$wp" ] || continue
  sudo install -m 644 "$wp" "$WALLPAPER_DIR/$(basename "$wp")"
done
DEFAULT_WP="$WALLPAPER_DIR/noctraos-sunset-peaks-2160p.jpg"
if [ -f "$DEFAULT_WP" ]; then
  as_user plasma-apply-wallpaperimage "$DEFAULT_WP" >/dev/null 2>&1 \
    || warn "Could not set the wallpaper now (no Plasma session yet); cycle with: noc bg set <name>"
  log "Wallpaper set (cycle with: noc bg next)"
fi

log "Installing the panel layout (applied once, from the session)..."
sudo mkdir -p "$PLASMA_SHARE"
sudo install -m 644 "$REPO_ROOT/configs/plasma/panel-layout.js" "$PLASMA_SHARE/panel-layout.js"
sudo install -m 755 "$REPO_ROOT/configs/plasma/apply-layout.sh" "$PLASMA_SHARE/apply-layout.sh"
sudo install -m 644 "$REPO_ROOT/configs/autostart/noctraos-plasma-layout.desktop" /etc/xdg/autostart/noctraos-plasma-layout.desktop

log "Desktop customization complete (the panel layout appears at the next login)."
