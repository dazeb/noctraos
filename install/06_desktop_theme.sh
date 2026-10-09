#!/usr/bin/env bash
# Module 06: desktop customization — Windows/KDE ergonomics on Zorin.
# Every step is warn-not-die: a schema drift must never abort the install.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if ! desktop_is_gnome; then
  warn "NOT APPLIED on this desktop: GNOME gsettings theme settings"
  exit 0
fi

gs() { as_user gsettings set "$@" 2>/dev/null || warn "gsettings failed: $*"; }

log "Window buttons to the right (Minimize, Maximize, Close)..."
gs org.gnome.desktop.wm.preferences button-layout ':minimize,maximize,close'

log "Enabling system dark mode..."
gs org.gnome.desktop.interface color-scheme 'prefer-dark'
# Module 08 selects the custom GTK theme; avoid resetting it on every run.

log "Pinning taskbar favorites (existing entries only)..."
# Microsoft renamed the stable desktop entry; older packages still use code.desktop.
VSCODE_DESKTOP=com.microsoft.VSCode.desktop
if ! desktop_file_exists "$VSCODE_DESKTOP"; then
  VSCODE_DESKTOP=code.desktop
fi
CANDIDATES=(
  zorin-menu.desktop
  org.gnome.Nautilus.desktop
  "$VSCODE_DESKTOP"
  io.missioncenter.MissionCenter.desktop
  org.gnome.Terminal.desktop
  noctraos-control.desktop
)
favorites=()
for c in "${CANDIDATES[@]}"; do
  # The Control Panel launcher is installed further down in this module, so on a first run only the repo has it yet.
  if desktop_file_exists "$c" || [ "$c" = noctraos-control.desktop ]; then
    favorites+=("$c")
  else
    warn "Skipping missing desktop entry: $c"
  fi
done
if [ "${#favorites[@]}" -gt 0 ]; then
  gvariant="[$(printf "'%s'," "${favorites[@]}" | sed 's/,$//')]"
  gs org.gnome.shell favorite-apps "$gvariant"
  log "Favorites: ${favorites[*]}"
fi

log "Installing AI agent launchers and the 'Agents' menu section..."
sudo mkdir -p /usr/local/share/applications /usr/share/desktop-directories \
              /etc/xdg/menus/applications-merged \
              /usr/local/share/icons/hicolor/scalable/apps \
              /usr/local/bin
sudo install -m 755 "$REPO_ROOT/bin/noctraos-agent" /usr/local/bin/noctraos-agent
sudo install -m 755 "$REPO_ROOT/bin/noctraos-hermes" /usr/local/bin/noctraos-hermes
sudo install -m 755 "$REPO_ROOT/bin/noctraos-welcome" /usr/local/bin/noctraos-welcome
sudo install -m 755 "$REPO_ROOT/bin/noctraos-appearance" /usr/local/bin/noctraos-appearance
sudo install -D -m 644 "$REPO_ROOT/configs/hermes/onboarding.md" /usr/local/share/noctraos/hermes/onboarding.md
install_launchers "$REPO_ROOT"
sudo install -m 644 "$REPO_ROOT/configs/applications/noctraos-agents.directory" \
  /usr/share/desktop-directories/
sudo install -m 644 "$REPO_ROOT/configs/xdg/noctraos-agents.menu" \
  /etc/xdg/menus/applications-merged/
sudo update-desktop-database >/dev/null 2>&1 || true
# Hermes ships its own icon; install the upstream artwork system-wide (see assets/icons/hermes/NOTICE.md).
for i in "$REPO_ROOT"/assets/icons/hermes/hicolor/*/apps/hermes.png; do
  [ -f "$i" ] || continue
  size="$(basename "$(dirname "$(dirname "$i")")")"
  cmp -s "$i" "/usr/local/share/icons/hicolor/$size/apps/hermes.png" 2>/dev/null \
    || sudo install -D -m 644 "$i" "/usr/local/share/icons/hicolor/$size/apps/hermes.png"
done
sudo gtk-update-icon-cache -q -t -f /usr/local/share/icons/hicolor 2>/dev/null || true
log "OK: Agents section — Hermes, Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code (Hermes preinstalled by module 11, the rest install-on-first-use)"

log "Installing AI-first application menu (replaces stock category tree)..."
sudo install -m 644 "$REPO_ROOT/configs/applications/noctraos-local-llm.directory" \
  /usr/share/desktop-directories/
if [ -f /etc/xdg/menus/gnome-applications.menu ] \
   && [ ! -f /etc/xdg/menus/gnome-applications.menu.orig ]; then
  sudo cp /etc/xdg/menus/gnome-applications.menu /etc/xdg/menus/gnome-applications.menu.orig
fi
sudo install -m 644 "$REPO_ROOT/configs/xdg/gnome-applications.menu" \
  /etc/xdg/menus/gnome-applications.menu
log "OK: menu sections — Agents, Local LLM, Development, Internet, Media, Utilities, System"

# GNOME app-grid folder so 'Agents' also exists in the All Apps grid.
AF="org.gnome.desktop.app-folders"
if as_user gsettings list-schemas 2>/dev/null | grep -q "^${AF}$"; then
  cur="$(as_user gsettings get $AF folder-children 2>/dev/null || echo '@as []')"
  case "$cur" in
    *noctraos-agents.folder*) : ;;
    '@as []'|'[]')
      as_user gsettings set $AF folder-children "['noctraos-agents.folder']" || warn "app-folders set failed" ;;
    *)
      as_user gsettings set $AF folder-children "${cur%]}, 'noctraos-agents.folder']" \
        || warn "app-folders append failed" ;;
  esac
  as_user gsettings set "$AF.folder:/org/gnome/Desktop/folders/noctraos-agents.folder/" name "Agents" \
    || warn "app-folder name failed"
  as_user gsettings set "$AF.folder:/org/gnome/Desktop/folders/noctraos-agents.folder/" \
    categories "['X-NoctraOS-Agents']" || warn "app-folder categories failed"
  log "OK: 'Agents' folder registered in the app grid"
fi

log "Applying polygonal wallpaper set..."
WALLPAPER_DIR="/usr/local/share/backgrounds/noctraos"
sudo mkdir -p "$WALLPAPER_DIR"
for wp in "$REPO_ROOT"/assets/wallpapers/*.jpg; do
  [ -f "$wp" ] || continue
  sudo install -m 644 "$wp" "$WALLPAPER_DIR/$(basename "$wp")"
done
# Default: the striking sunset scene; aurora for the lock screen.
DEFAULT_WP="$WALLPAPER_DIR/noctraos-sunset-peaks-2160p.jpg"
LOCK_WP="$WALLPAPER_DIR/noctraos-aurora-peaks-2160p.jpg"
if [ -f "$DEFAULT_WP" ]; then
  gs org.gnome.desktop.background picture-uri "file://$DEFAULT_WP"
  gs org.gnome.desktop.background picture-uri-dark "file://$DEFAULT_WP"
  gs org.gnome.desktop.background picture-options 'zoom'
  [ -f "$LOCK_WP" ] && gs org.gnome.desktop.screensaver picture-uri "file://$LOCK_WP"
  log "Wallpaper set (cycle with: noc bg next)"
fi

if as_user gsettings list-keys org.gnome.desktop.interface 2>/dev/null \
  | grep '^accent-color$' >/dev/null; then
  log "Setting desktop accent to orange..."
  gs org.gnome.desktop.interface accent-color 'orange'
fi

if as_user gsettings list-schemas 2>/dev/null | grep -q '^org\.gnome\.shell\.extensions\.ding$'; then
  log "Ensuring desktop icons (DING) show Home and Trash..."
  gs org.gnome.shell.extensions.ding show-home true
  gs org.gnome.shell.extensions.ding show-trash true
fi

log "Desktop customization complete (some settings may need a re-login to fully apply)."
