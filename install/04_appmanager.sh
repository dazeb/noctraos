#!/usr/bin/env bash
# Module 04c: AppManager (github.com/kem-a/AppManager) — drag-and-drop AppImage
# installer and updater. Double-clicking an .AppImage opens its install window.
# The release AppImage is self-contained (bundled uruntime, no FUSE needed to run
# it), so it is installed system-wide to /opt and linked into /usr/local/bin.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

DEST=/opt/appmanager
BIN=/usr/local/bin/app-manager
API=https://api.github.com/repos/kem-a/AppManager/releases/latest

case "$(uname -m)" in
  x86_64)  ARCH=x86_64 ;;
  aarch64) ARCH=aarch64 ;;
  *) warn "AppManager has no build for $(uname -m); skipping"; exit 0 ;;
esac

ENTRY=/usr/local/share/applications/com.github.AppManager.desktop
ICON=/usr/share/icons/hicolor/scalable/apps/com.github.AppManager.svg

installed_version() { cat "$DEST/VERSION" 2>/dev/null || true; }
# VERSION is written last, so "current" means every artifact is in place.
fully_installed() { [ -x "$BIN" ] && [ -f "$ENTRY" ] && [ -f "$ICON" ]; }

# name, url, sha256 of the newest release asset for this architecture.
release_json="$(curl -fsSL --max-time 20 "$API" 2>/dev/null || true)"
if [ -z "$release_json" ]; then
  if fully_installed; then
    log "OK: AppManager $(installed_version) present (could not check for a newer release)"
    exit 0
  fi
  die "could not reach the GitHub API to find the AppManager release"
fi
read -r TAG URL SHA < <(ARCH="$ARCH" python3 -c '
import json, os, sys
r = json.load(sys.stdin)
for a in r.get("assets", []):
    n = a["name"]
    if n.endswith(os.environ["ARCH"] + ".AppImage"):
        print(r["tag_name"], a["browser_download_url"], (a.get("digest") or "").removeprefix("sha256:"))
        break
' <<<"$release_json")
[ -n "${URL:-}" ] || die "no $ARCH AppImage in the latest AppManager release"
[ -n "${SHA:-}" ] || die "release publishes no sha256 digest for $URL; refusing an unverified download"

if fully_installed && [ "$(installed_version)" = "$TAG" ]; then
  log "OK: AppManager $TAG already installed"
else
  log "Installing AppManager $TAG"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL --retry 3 -o "$tmp/AppManager.AppImage" "$URL"
  echo "$SHA  $tmp/AppManager.AppImage" | sha256sum -c - >/dev/null \
    || die "AppManager checksum mismatch — download discarded"
  chmod +x "$tmp/AppManager.AppImage"
  # Pull the desktop entry and icon out of the image (extract only; nothing runs).
  ( cd "$tmp" && ./AppManager.AppImage --appimage-extract 'com.github.AppManager.*' >/dev/null 2>&1 ) \
    || ( cd "$tmp" && ./AppManager.AppImage --appimage-extract >/dev/null 2>&1 ) \
    || die "could not unpack the AppManager AppImage"

  sudo install -d "$DEST"
  sudo install -m 755 "$tmp/AppManager.AppImage" "$DEST/AppManager.AppImage"

  # The shipped entry hardcodes /usr/bin/app-manager (its distro-package path).
  [ -f "$tmp/squashfs-root/com.github.AppManager.desktop" ] && [ -f "$tmp/squashfs-root/com.github.AppManager.svg" ] \
    || die "AppManager AppImage is missing its desktop entry or icon (layout changed?)"
  sudo install -d "$(dirname "$ENTRY")"
  sed -e "s|^Exec=.*|Exec=$BIN %u|" -e "s|^TryExec=.*|TryExec=$BIN|" \
    "$tmp/squashfs-root/com.github.AppManager.desktop" | sudo tee "$ENTRY" >/dev/null
  sudo install -D -m 644 "$tmp/squashfs-root/com.github.AppManager.svg" "$ICON"
  sudo gtk-update-icon-cache -q -f /usr/share/icons/hicolor >/dev/null 2>&1 || true

  # Commit last: the binary link and the version marker only appear once the
  # metadata above is in place, so a failed run is retried in full.
  sudo ln -sf "$DEST/AppManager.AppImage" "$BIN"
  echo "$TAG" | sudo tee "$DEST/VERSION" >/dev/null
fi

# Make AppManager the default opener for .AppImage files and appimg:// links
# (system-wide default; a user's own choice in ~/.config/mimeapps.list still wins).
MIMEAPPS=/etc/xdg/mimeapps.list
DESKTOP=com.github.AppManager.desktop
for mt in application/vnd.appimage application/x-iso9660-appimage x-scheme-handler/appimg; do
  if [ -f "$MIMEAPPS" ] && grep -F "$mt=" "$MIMEAPPS" >/dev/null; then
    continue
  fi
  if [ -f "$MIMEAPPS" ] && grep -Fx '[Default Applications]' "$MIMEAPPS" >/dev/null; then
    sudo sed -i "/^\[Default Applications\]/a $mt=$DESKTOP" "$MIMEAPPS"
  elif [ -f "$MIMEAPPS" ]; then
    printf '\n[Default Applications]\n%s=%s\n' "$mt" "$DESKTOP" | sudo tee -a "$MIMEAPPS" >/dev/null
  else
    printf '[Default Applications]\n%s=%s\n' "$mt" "$DESKTOP" | sudo tee "$MIMEAPPS" >/dev/null
  fi
done
sudo update-desktop-database /usr/local/share/applications >/dev/null 2>&1 || true
log "AppManager ready (open an .AppImage, or run: app-manager --help)."
