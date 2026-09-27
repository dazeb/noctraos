#!/usr/bin/env bash
# Module 08: shell reskin — ZorinAI-Dark shell theme + white category icons.
#
# Derives a full GNOME Shell theme from the installed Zorin dark shell CSS,
# sharpens the measured border radii (>=10px -> 4px, pills -> 4px, 5-9px -> 3px)
# and appends a cyberpunk-neon override block (dark menus, pink/purple/green
# accents). Activates it through the user-theme extension. Also installs solid
# white category icons so every icon in the start menu matches.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

BASE_THEME="/usr/share/themes/ZorinBlue-Dark"
BASE_GTK_THEME="/usr/share/themes/ZorinPurple-Dark"
THEME_NAME="ZorinAI-Dark"
THEME_DIR="/usr/share/themes/$THEME_NAME"

if [ -d "$BASE_GTK_THEME/gtk-3.0" ]; then
  log "Building $THEME_NAME GTK theme from ZorinPurple-Dark..."
  sudo mkdir -p "$THEME_DIR"
  for component in gtk-2.0 gtk-3.0 gtk-4.0; do
    [ -d "$BASE_GTK_THEME/$component" ] && \
      sudo cp -r "$BASE_GTK_THEME/$component" "$THEME_DIR/"
  done
  sudo python3 - "$THEME_DIR" <<'PYEOF'
import pathlib
import re
import sys

for path in pathlib.Path(sys.argv[1]).glob("gtk-*/gtk*.css"):
    css = path.read_text()
    # Keep zero and tiny radii; sharpen the large Zorin controls and corners.
    css = re.sub(
        r"border-radius\s*:[^;]+;",
        lambda match: re.sub(
            r"\b(\d+)px\b",
            lambda radius: f"{min(int(radius.group(1)), 4)}px",
            match.group(0),
        ),
        css,
    )
    path.write_text(css)
PYEOF
  sudo tee "$THEME_DIR/index.theme" >/dev/null <<'EOF'
[Desktop Entry]
Type=X-GNOME-Metatheme
Name=ZorinAI-Dark
Comment=Zorin AI dark desktop theme

[X-GNOME-Metatheme]
GtkTheme=ZorinAI-Dark
IconTheme=ZorinPurple-Dark
CursorTheme=Adwaita
ButtonLayout=:minimize,maximize,close
EOF
  as_user gsettings set org.gnome.desktop.interface gtk-theme "$THEME_NAME" \
    || warn "gtk-theme set failed"
else
  warn "ZorinPurple-Dark GTK theme not found — GTK reskin skipped"
fi

log "Building $THEME_NAME shell theme from ZorinBlue-Dark..."
if [ ! -f "$BASE_THEME/gnome-shell/gnome-shell.css" ]; then
  warn "ZorinBlue-Dark shell CSS not found — reskin skipped"
else
  sudo mkdir -p "$THEME_DIR/gnome-shell"
  sudo cp -r "$BASE_THEME/gnome-shell/." "$THEME_DIR/gnome-shell/"

  # Patch: clamp border radii + append neon overrides.
  sudo python3 - "$THEME_DIR/gnome-shell/gnome-shell.css" <<'PYEOF'
import re
import sys

path = sys.argv[1]
css = open(path).read()


def clamp_radius(match):
    v = int(match.group(1))
    if v >= 999:
        v = 4
    elif v >= 10:
        v = 4
    elif v >= 5:
        v = 3
    return f"border-radius: {v}px"


css = re.sub(r"border-radius:\s*(\d+)px", clamp_radius, css)

css += """

/* ==== zorin-ai cyberpunk overrides ==== */
.popup-menu-content, .candidate-popup-content {
  background-color: rgba(7, 9, 14, 0.97);
  border: 1px solid rgba(255, 45, 149, 0.35);
  border-radius: 4px;
  color: #f2f2f7;
}
.popup-menu-item.selected {
  background-color: rgba(161, 36, 255, 0.22);
  border-radius: 3px;
  color: #ffffff;
}
.popup-menu-item:checked { background-color: rgba(57, 255, 136, 0.14); }
.popup-sub-menu {
  background-color: rgba(13, 16, 24, 0.98);
  border-radius: 3px;
}
.popup-menu-item { color: #e8e8f0; }
.search-entry {
  border-radius: 3px;
  border: 1px solid rgba(255, 45, 149, 0.35);
  color: #f2f2f7;
}
.search-entry:focus {
  border-color: rgba(255, 45, 149, 0.8);
  box-shadow: 0 0 6px rgba(255, 45, 149, 0.35);
}
StEntry { selection-background-color: rgba(161, 36, 255, 0.45); }
StScrollBar-StBin { background-color: rgba(161, 36, 255, 0.25); }
"""
open(path, "w").write(css)
print("patched:", path)
PYEOF

  # Activate through the user-theme extension (applies on next login).
  if as_user gsettings list-schemas 2>/dev/null | grep '^org\.gnome\.shell\.extensions\.user-theme$' >/dev/null; then
    as_user gsettings set org.gnome.shell.extensions.user-theme name "$THEME_NAME" \
      || warn "could not set user-theme"
    log "OK: user-theme set to $THEME_NAME"
  else
    warn "user-theme extension schema missing — shell theme not activated"
  fi
fi

log "Installing solid white menu icons..."
ICON_DIR="/usr/local/share/icons/hicolor/scalable/apps"
sudo mkdir -p "$ICON_DIR"
for i in "$REPO_ROOT"/assets/icons/overrides/*.svg; do
  [ -f "$i" ] && sudo install -m 644 "$i" "$ICON_DIR/$(basename "$i")"
done
for i in "$REPO_ROOT"/assets/icons/zorin-ai-*.svg; do
  [ -f "$i" ] && sudo install -m 644 "$i" "$ICON_DIR/$(basename "$i")"
done
sudo gtk-update-icon-cache -q -t -f /usr/local/share/icons/hicolor 2>/dev/null || true

# Match the terminal, agent manager, and system monitor to the shell palette.
if as_user gsettings list-schemas 2>/dev/null | grep '^org\.gnome\.Terminal\.ProfilesList$' >/dev/null; then
  profile_id="$(as_user gsettings get org.gnome.Terminal.ProfilesList default 2>/dev/null | tr -d "'" || true)"
  if [ -n "$profile_id" ]; then
    profile="org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:$profile_id/"
    as_user gsettings set "$profile" use-theme-colors false || warn "terminal colors unavailable"
    as_user gsettings set "$profile" background-color '#0b0d14' || warn "terminal background unavailable"
    as_user gsettings set "$profile" foreground-color '#f2f2f7' || warn "terminal foreground unavailable"
    as_user gsettings set "$profile" palette "['#0b0d14', '#ff5b79', '#39ff88', '#f9c66e', '#58b8ff', '#a124ff', '#5be1d6', '#f2f2f7', '#55566a', '#ff8aa8', '#81ffad', '#ffda94', '#8ed0ff', '#cf8aff', '#9af0e9', '#ffffff']" \
      || warn "terminal palette unavailable"
    as_user gsettings set "$profile" use-system-font false || warn "terminal font setting unavailable"
    as_user gsettings set "$profile" font 'JetBrainsMono Nerd Font 11' || warn "terminal font unavailable"
  fi
else
  warn "GNOME Terminal profile schema missing — terminal palette skipped"
fi

user_group="$(id -gn "$TARGET_USER")"
as_user mkdir -p "$TARGET_HOME/.config/herdr" "$TARGET_HOME/.config/btop/themes"
if ! as_user test -f "$TARGET_HOME/.config/herdr/config.toml"; then
  sudo install -o "$TARGET_USER" -g "$user_group" -m 644 \
    "$REPO_ROOT/configs/theme/herdr.toml" "$TARGET_HOME/.config/herdr/config.toml"
fi
sudo install -o "$TARGET_USER" -g "$user_group" -m 644 \
  "$REPO_ROOT/configs/theme/zorin-ai-btop.theme" \
  "$TARGET_HOME/.config/btop/themes/zorin-ai.theme"
if ! as_user test -f "$TARGET_HOME/.config/btop/btop.conf"; then
  as_user sh -c 'printf "color_theme = \"zorin-ai\"\n" > "$HOME/.config/btop/btop.conf"'
fi
log "Shell reskin complete — sign out/in (or reboot) to see every change."
