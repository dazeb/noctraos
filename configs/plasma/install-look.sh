#!/usr/bin/env bash
# install-look.sh <root> — the system-wide NoctraOS look on KDE Plasma (flavour kubuntu), written into <root>: "/" on a
# running system (install/desktop/plasma/08_shell_theme.sh), the unpacked squashfs when the kubuntu ISO is built
# (iso/flavours/kubuntu.sh), so the very first login already looks like NoctraOS. One implementation for both.
#
#   - the Global Theme dev.noctraos.desktop (System Settings > Colors & Themes): splash, previews, defaults and the panel
#     layout from configs/plasma, so "apply the layout too" gives the NoctraOS panel, not Breeze's
#   - the wallpapers as Plasma wallpaper packages, listed by name in the wallpaper picker
#   - the colour scheme for every account (module 06 also installs it for the person who ran the installer)
#   - the login screen: Breeze's SDDM theme with the NoctraOS background and logo. theme.conf.user is written only when it
#     is missing or ours, and /etc/sddm.conf.d/30-noctraos.conf selects the theme; System Settings > Login Screen writes
#     kde_settings.conf, which sorts after it, so a choice made there wins
#   - system defaults for the splash and the lock screen (/etc/xdg/ksplashrc and kscreenlockerrc, files no package owns;
#     Kubuntu's own defaults sit lower in the config path); a person's own choice in ~/.config still wins
#   - "About this System" for accounts created later (/etc/skel/.config/kcm-about-distrorc)
#
# Idempotent. A file someone else wrote is left alone and the run says so. Artwork: scripts/render-kubuntu-branding.py.
set -Eeuo pipefail

ROOT_DIR="${1:?usage: install-look.sh <root>}"
ROOT_DIR="${ROOT_DIR%/}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ASSETS="$REPO/assets/plasma"
MARKER="# Written by NoctraOS (configs/plasma/install-look.sh)."
LNF_ID="dev.noctraos.desktop"
SHARE="$ROOT_DIR/usr/local/share"
LOOK="/usr/local/share/noctraos/plasma/login"        # as the running system sees it
VERSION="$(tr -d '[:space:]' < "$REPO/VERSION")"

say() { printf '  %s\n' "$*"; }

# put <src> <dest>: copy when different, mode 644, parents created.
put() { cmp -s "$1" "$2" 2>/dev/null || install -D -m 644 "$1" "$2"; }

# ours_or_missing <file>: true when we may (re)write it.
ours_or_missing() { [ ! -e "$1" ] || grep -Fqx "$MARKER" "$1"; }

# write_ours <file> <content>: write a config file of ours, or leave someone else's alone.
write_ours() {
  local file="$1" content="$2"
  if ours_or_missing "$file"; then
    mkdir -p "$(dirname "$file")"
    printf '%s\n%s' "$MARKER" "$content" > "$file.noctraos-tmp"
    if cmp -s "$file.noctraos-tmp" "$file" 2>/dev/null; then rm -f "$file.noctraos-tmp"; else mv "$file.noctraos-tmp" "$file"; fi
    chmod 644 "$file"
  else
    say "kept (not ours): ${file#"$ROOT_DIR"}"
  fi
}

# Wallpaper id from a file name: noctraos-sunset-peaks-2160p.jpg -> NoctraOS-SunsetPeaks; title: Sunset Peaks.
wallpaper_slug() { local b; b="$(basename "$1" .jpg)"; b="${b#noctraos-}"; printf '%s' "${b%-2160p}"; }
wallpaper_title() { wallpaper_slug "$1" | tr '-' '\n' | sed 's/^./\U&/' | paste -sd' '; }
wallpaper_id() { printf 'NoctraOS-%s' "$(wallpaper_title "$1" | tr -d ' ')"; }

# 1. Global Theme package.
lnf="$SHARE/plasma/look-and-feel/$LNF_ID"
while IFS= read -r -d '' f; do
  put "$f" "$lnf/${f#"$ASSETS/look-and-feel/$LNF_ID/"}"
done < <(find "$ASSETS/look-and-feel/$LNF_ID" -type f -print0)
# The panel layout, with the VS Code launcher this root has (the same substitution apply-layout.sh makes in a session).
layout="$(NOCTRAOS_PLASMA_DIR="$REPO/configs/plasma" \
  NOCTRAOS_APP_DIRS="$ROOT_DIR/usr/share/applications:$SHARE/applications:$ROOT_DIR/var/lib/flatpak/exports/share/applications" \
  bash "$REPO/configs/plasma/apply-layout.sh" --print-script)"
mkdir -p "$lnf/contents/layouts"
printf '%s\n' "$layout" > "$lnf/contents/layouts/org.kde.plasma.desktop-layout.js.tmp"
mv "$lnf/contents/layouts/org.kde.plasma.desktop-layout.js.tmp" "$lnf/contents/layouts/org.kde.plasma.desktop-layout.js"
say "Global Theme: $LNF_ID"

# 2. Wallpaper packages (one per committed 4K wallpaper).
for wp in "$REPO"/assets/wallpapers/*.jpg; do
  [ -f "$wp" ] || continue
  id="$(wallpaper_id "$wp")"
  pkg="$SHARE/wallpapers/$id"
  put "$wp" "$pkg/contents/images/3840x2160.jpg"
  meta="$(printf '{\n    "KPlugin": {\n        "Authors": [\n            {\n                "Email": "admin@noctraos.dev",\n                "Name": "NoctraOS"\n            }\n        ],\n        "Id": "%s",\n        "License": "MIT",\n        "Name": "%s"\n    }\n}' "$id" "$(wallpaper_title "$wp")")"
  [ "$(cat "$pkg/metadata.json" 2>/dev/null)" = "$meta" ] || printf '%s\n' "$meta" > "$pkg/metadata.json"
  chmod 644 "$pkg/metadata.json"
done
say "wallpapers: $(find "$SHARE/wallpapers" -maxdepth 1 -name 'NoctraOS-*' | wc -l) packages"

# 3. Colour scheme for every account, and the logo the About page and the Start button use.
put "$REPO/configs/plasma/NoctraOSDark.colors" "$SHARE/color-schemes/NoctraOSDark.colors"
put "$REPO/assets/icons/noctraos-logo.svg" "$SHARE/icons/hicolor/scalable/apps/noctraos-logo.svg"

# 4. Login screen (SDDM, Breeze theme) and the shared login/lock-screen pictures.
put "$ASSETS/login/background.jpg" "$ROOT_DIR$LOOK/background.jpg"
put "$ASSETS/login/logo.png" "$ROOT_DIR$LOOK/logo.png"
if [ -f "$ROOT_DIR/usr/share/sddm/themes/breeze/metadata.desktop" ]; then
  write_ours "$ROOT_DIR/usr/share/sddm/themes/breeze/theme.conf.user" "[General]
type=image
color=#121212
background=$LOOK/background.jpg
showlogo=shown
logo=$LOOK/logo.png
"
  write_ours "$ROOT_DIR/etc/sddm.conf.d/30-noctraos.conf" "[Theme]
Current=breeze
"
  say "login screen: Breeze with the NoctraOS background"
else
  say "NOT APPLIED: login screen (SDDM's Breeze theme is not installed)"
fi

# 5. Splash after login and the lock screen picture, as system defaults.
write_ours "$ROOT_DIR/etc/xdg/ksplashrc" "[KSplash]
Engine=KSplashQML
Theme=$LNF_ID
"
write_ours "$ROOT_DIR/etc/xdg/kscreenlockerrc" "[Greeter][Wallpaper][org.kde.image][General]
Image=file://$LOOK/background.jpg
PreviewImage=file://$LOOK/background.jpg
"

# 6. About this System, for accounts created from now on (module 08 writes it for existing ones).
write_ours "$ROOT_DIR/etc/skel/.config/kcm-about-distrorc" "[General]
LogoPath=/usr/local/share/icons/hicolor/scalable/apps/noctraos-logo.svg
Name=NoctraOS
UseOSReleaseVersion=false
Version=$VERSION
Website=https://noctraos.dev/
"
say "splash, lock screen and About this System defaults"
