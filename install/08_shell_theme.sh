#!/usr/bin/env bash
# Module 08: Omarchy-inspired NoctraOS-Dark, derived from installed Zorin themes.
# Desktop operations are best-effort. Never override user GTK CSS or GTK_THEME.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

BASE_THEME="/usr/share/themes/ZorinBlue-Dark"
BASE_GTK_THEME="/usr/share/themes/ZorinPurple-Dark"
THEME_NAME="NoctraOS-Dark"
THEME_DIR="/usr/share/themes/$THEME_NAME"
PALETTE="$REPO_ROOT/configs/theme/palette.json"

# gsettings accepts GVariant literals. Compare first so reruns emit no changes.
theme_set() {
  local current
  current="$(as_user gsettings get "$1" "$2" 2>/dev/null || true)"
  if [ "$current" != "$3" ]; then
    as_user gsettings set "$1" "$2" "$3" || warn "Theme setting unavailable: $1 $2"
  fi
}
install_theme_file() {
  if ! cmp -s "$1" "$2"; then
    sudo install -D -m 644 "$1" "$2" || warn "Theme file unavailable: $2"
  fi
}

for component in gtk-3.0 gtk-4.0; do
  if [ -f "$BASE_GTK_THEME/$component/gtk.css" ]; then
    sudo python3 "$REPO_ROOT/scripts/build-desktop-theme.py" \
      --base "$BASE_GTK_THEME/$component" --output "$THEME_DIR/$component" \
      --overlay "$REPO_ROOT/configs/theme/gtk.css" --css-name gtk.css \
      --remap "$REPO_ROOT/configs/theme/gtk-remap.json" --palette "$PALETTE" \
      --radius "$(jq -r '.radius' "$PALETTE")" \
      || warn "$component reskin failed"
  else
    warn "$component base theme not found — skipped"
  fi
done
if [ -d "$BASE_GTK_THEME/gtk-2.0" ] \
  && ! diff -qr "$BASE_GTK_THEME/gtk-2.0" "$THEME_DIR/gtk-2.0" >/dev/null 2>&1; then
  sudo mkdir -p "$THEME_DIR" && sudo cp -r "$BASE_GTK_THEME/gtk-2.0" "$THEME_DIR/" \
    || warn "GTK 2 fallback unavailable"
fi
install_theme_file "$REPO_ROOT/configs/theme/index.theme" "$THEME_DIR/index.theme"
if [ -f "$THEME_DIR/gtk-3.0/gtk.css" ]; then
  theme_set org.gnome.desktop.interface gtk-theme "'$THEME_NAME'"
fi
# Neutral grey icons: Zorin's own ZorinGrey-Dark, plus a small derived theme that
# fixes the few icons that still come out bright (the cyan Desktop folder).
if [ -d /usr/share/icons/ZorinGrey-Dark ]; then
  ICON_SRC="$REPO_ROOT/assets/icons/noctraos-theme"
  ICON_DIR="/usr/share/icons/NoctraOS"
  install_theme_file "$ICON_SRC/index.theme" "$ICON_DIR/index.theme"
  for icon in "$ICON_SRC"/scalable/places/*.svg; do
    install_theme_file "$icon" "$ICON_DIR/scalable/places/$(basename "$icon")"
  done
  sudo gtk-update-icon-cache -q -t -f "$ICON_DIR" 2>/dev/null || true
  theme_set org.gnome.desktop.interface icon-theme "'NoctraOS'"
else
  warn "ZorinGrey-Dark icon theme not found — icons left as is"
fi

if [ -f "$BASE_THEME/gnome-shell/gnome-shell.css" ]; then
  if sudo python3 "$REPO_ROOT/scripts/build-desktop-theme.py" \
    --base "$BASE_THEME/gnome-shell" --output "$THEME_DIR/gnome-shell" \
    --overlay "$REPO_ROOT/configs/theme/gnome-shell.css" --css-name gnome-shell.css \
    --remap "$REPO_ROOT/configs/theme/shell-remap.json" --palette "$PALETTE" \
    --radius "$(jq -r '.radius' "$PALETTE")"; then
    if as_user gsettings list-schemas 2>/dev/null | grep '^org\.gnome\.shell\.extensions\.user-theme$' >/dev/null; then
      theme_set org.gnome.shell.extensions.user-theme name "'$THEME_NAME'"
    else
      warn "user-theme schema missing — shell theme not activated"
    fi
  else
    warn "Shell reskin failed"
  fi
else
  warn "ZorinBlue-Dark shell CSS not found — shell reskin skipped"
fi

log "Installing solid white menu icons..."
ICON_DIR="/usr/local/share/icons/hicolor/scalable/apps"
sudo mkdir -p "$ICON_DIR" || warn "Icon directory unavailable"
for i in "$REPO_ROOT"/assets/icons/overrides/*.svg; do
  [ -f "$i" ] && install_theme_file "$i" "$ICON_DIR/$(basename "$i")"
done
for i in "$REPO_ROOT"/assets/icons/noctraos-*.svg; do
  [ -f "$i" ] && install_theme_file "$i" "$ICON_DIR/$(basename "$i")"
done
sudo gtk-update-icon-cache -q -t -f /usr/local/share/icons/hicolor 2>/dev/null || true


if as_user gsettings list-schemas 2>/dev/null | grep '^org\.gnome\.Terminal\.ProfilesList$' >/dev/null; then
  profile_id="$(as_user gsettings get org.gnome.Terminal.ProfilesList default 2>/dev/null | tr -d "'" || true)"
  if [ -n "$profile_id" ]; then
    profile="org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:$profile_id/"
    background="$(jq -r '.colors.background' "$PALETTE" || true)"
    foreground="$(jq -r '.colors.foreground' "$PALETTE" || true)"
    terminal_palette="$(jq -r '.terminal | "[" + (map("\u0027" + . + "\u0027") | join(", ")) + "]"' "$PALETTE" || true)"
    terminal_font="$(jq -r '.font + " 11"' "$PALETTE" || true)"
    if [ -n "$background" ] && [ -n "$foreground" ] && [ -n "$terminal_palette" ]; then
      theme_set "$profile" use-theme-colors false
      theme_set "$profile" background-color "'$background'"
      theme_set "$profile" foreground-color "'$foreground'"
      theme_set "$profile" palette "$terminal_palette"
      theme_set "$profile" use-system-font false
      theme_set "$profile" font "'$terminal_font'"
    else
      warn "Terminal palette could not be read"
    fi
  fi
else
  warn "GNOME Terminal profile schema missing — terminal palette skipped"
fi

user_group="$(id -gn "$TARGET_USER")"
as_user mkdir -p "$TARGET_HOME/.config/herdr" "$TARGET_HOME/.config/btop/themes" \
  || warn "App theme directories unavailable"
# Upgrade our known old default, but keep customized Herdr configuration.
if ! as_user test -f "$TARGET_HOME/.config/herdr/config.toml" \
  || cmp -s "$TARGET_HOME/.config/herdr/config.toml" "$REPO_ROOT/configs/theme/legacy/herdr.toml"; then
  sudo install -o "$TARGET_USER" -g "$user_group" -m 644 \
    "$REPO_ROOT/configs/theme/herdr.toml" "$TARGET_HOME/.config/herdr/config.toml" \
    || warn "Herdr palette unavailable"
fi
if ! cmp -s "$REPO_ROOT/configs/theme/noctraos-btop.theme" "$TARGET_HOME/.config/btop/themes/noctraos.theme"; then
  sudo install -o "$TARGET_USER" -g "$user_group" -m 644 \
    "$REPO_ROOT/configs/theme/noctraos-btop.theme" "$TARGET_HOME/.config/btop/themes/noctraos.theme" \
    || warn "btop palette unavailable"
fi
if ! as_user test -f "$TARGET_HOME/.config/btop/btop.conf"; then
  as_user sh -c 'printf "color_theme = \"noctraos\"\n" > "$HOME/.config/btop/btop.conf"' \
    || warn "btop configuration unavailable"
fi
log "Omarchy-inspired desktop complete — sign out/in for all shell changes."
