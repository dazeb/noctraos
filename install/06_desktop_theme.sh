#!/usr/bin/env bash
# Module 06: desktop customization — Windows/KDE ergonomics on Zorin.
# Every step is warn-not-die: a schema drift must never abort the install.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

gs() { as_user gsettings set "$@" 2>/dev/null || warn "gsettings failed: $*"; }

log "Window buttons to the right (Minimize, Maximize, Close)..."
gs org.gnome.desktop.wm.preferences button-layout ':minimize,maximize,close'

log "Enabling system dark mode..."
gs org.gnome.desktop.interface color-scheme 'prefer-dark'
gs org.gnome.desktop.interface gtk-theme 'ZorinBlue-Dark'

log "Pinning taskbar favorites (existing entries only)..."
CANDIDATES=(
  zorin-menu.desktop
  org.gnome.Nautilus.desktop
  codium.desktop
  xyz.chatboxapp.app.desktop
  io.missioncenter.MissionCenter.desktop
  org.gnome.Terminal.desktop
)
favorites=()
for c in "${CANDIDATES[@]}"; do
  if desktop_file_exists "$c"; then
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
sudo install -m 755 "$REPO_ROOT/bin/zorin-ai-agent" /usr/local/bin/zorin-ai-agent
for f in "$REPO_ROOT"/configs/applications/*.desktop; do
  [ -f "$f" ] && sudo install -m 644 "$f" /usr/local/share/applications/
done
sudo install -m 644 "$REPO_ROOT/configs/applications/zorin-ai-agents.directory" \
  /usr/share/desktop-directories/
sudo install -m 644 "$REPO_ROOT/configs/xdg/zorin-ai-agents.menu" \
  /etc/xdg/menus/applications-merged/
for i in "$REPO_ROOT"/assets/icons/zorin-ai-*.svg; do
  [ -f "$i" ] && sudo install -m 644 "$i" /usr/local/share/icons/hicolor/scalable/apps/
done
sudo update-desktop-database >/dev/null 2>&1 || true
sudo gtk-update-icon-cache -q -t -f /usr/local/share/icons/hicolor 2>/dev/null || true
log "OK: Agents section — Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code (install-on-first-use)"

log "Installing AI-first application menu (replaces stock category tree)..."
sudo install -m 644 "$REPO_ROOT/configs/applications/zorin-ai-local-llm.directory" \
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
    *zorin-ai-agents.folder*) : ;;
    '@as []'|'[]')
      as_user gsettings set $AF folder-children "['zorin-ai-agents.folder']" || warn "app-folders set failed" ;;
    *)
      as_user gsettings set $AF folder-children "${cur%]}, 'zorin-ai-agents.folder']" \
        || warn "app-folders append failed" ;;
  esac
  as_user gsettings set "$AF.folder:/org/gnome/Desktop/folders/zorin-ai-agents.folder/" name "Agents" \
    || warn "app-folder name failed"
  as_user gsettings set "$AF.folder:/org/gnome/Desktop/folders/zorin-ai-agents.folder/" \
    categories "['X-ZorinAI-Agents']" || warn "app-folder categories failed"
  log "OK: 'Agents' folder registered in the app grid"
fi

log "Applying polygonal wallpaper set..."
WALLPAPER_DIR="/usr/local/share/backgrounds/zorin-ai"
sudo mkdir -p "$WALLPAPER_DIR"
# drop any previous-generation wallpapers
sudo rm -f "$WALLPAPER_DIR"/zorin-ai-midnight-ridges-*.jpg \
           "$WALLPAPER_DIR"/zorin-ai-dusk-valley-*.jpg \
           "$WALLPAPER_DIR"/zorin-ai-teal-forest-*.jpg \
           "$WALLPAPER_DIR"/zorin-ai-storm-coast-*.jpg \
           "$WALLPAPER_DIR"/zorin-ai-ember-minimal-*.jpg
for wp in "$REPO_ROOT"/assets/wallpapers/*.jpg; do
  [ -f "$wp" ] || continue
  sudo install -m 644 "$wp" "$WALLPAPER_DIR/$(basename "$wp")"
done
# Default: the striking sunset scene; aurora for the lock screen.
DEFAULT_WP="$WALLPAPER_DIR/zorin-ai-sunset-peaks-2160p.jpg"
LOCK_WP="$WALLPAPER_DIR/zorin-ai-aurora-peaks-2160p.jpg"
if [ -f "$DEFAULT_WP" ]; then
  gs org.gnome.desktop.background picture-uri "file://$DEFAULT_WP"
  gs org.gnome.desktop.background picture-uri-dark "file://$DEFAULT_WP"
  gs org.gnome.desktop.background picture-options 'zoom'
  [ -f "$LOCK_WP" ] && gs org.gnome.desktop.screensaver picture-uri "file://$LOCK_WP"
  log "Wallpaper set (cycle with: zom bg next)"
fi

if as_user gsettings list-keys org.gnome.desktop.interface 2>/dev/null \
  | grep '^accent-color$' >/dev/null; then
  log "Setting desktop accent to purple..."
  gs org.gnome.desktop.interface accent-color 'purple'
fi

if as_user gsettings list-schemas 2>/dev/null | grep -q '^org\.gnome\.shell\.extensions\.ding$'; then
  log "Ensuring desktop icons (DING) show Home and Trash..."
  gs org.gnome.shell.extensions.ding show-home true
  gs org.gnome.shell.extensions.ding show-trash true
fi

log "Desktop customization complete (some settings may need a re-login to fully apply)."
