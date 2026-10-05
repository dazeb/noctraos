#!/usr/bin/env bash
# rebrand-labels.sh — replaces the user-facing "Zorin" names in the image with NoctraOS.
# Sourced by build-noctraos-iso.sh.
#
#   rebrand_labels <squashfs-root> <version>
#
# Zorin OS stays the upstream base and is still named as such in /etc/noctraos-release and
# the docs. What changes here is what a person sees: Settings > About, the console banner,
# the session picker, the launcher grid, the wallpaper picker, the live session's host and
# user name. What deliberately does NOT change: `ID=zorin` and `ID_LIKE` in os-release and
# `DISTRIB_ID` in lsb-release (Zorin's and Ubuntu's own tools key on them), the apt
# origins, package names and the `:zorin` gsettings groups.
#
# Everything is edited in place with exact-match guards, so a base image that changes shape
# fails the build instead of shipping a half-renamed system.

rebrand_labels() {
  local root="$1" version="$2" f
  [ -n "$version" ] || { echo "rebrand_labels: no version" >&2; return 1; }
  python3 - "$root" "$version" <<'PY' || return 1
import pathlib, re, sys

root, version = pathlib.Path(sys.argv[1]), sys.argv[2]

def edit(rel, fn):
    path = root / rel
    old = path.read_text()
    new = fn(old)
    if new == old:
        sys.exit(f"rebrand: nothing to change in {rel} (base image differs from what this expects)")
    path.write_text(new)

def set_keys(values):
    def run(text):
        for key, value in values.items():
            text, n = re.subn(rf'(?m)^{key}=.*$', f'{key}={value}', text)
            if n != 1:
                sys.exit(f"rebrand: expected one {key}= line, found {n}")
        return text
    return run

# Settings > About, `lsb_release -d`, the console banner. /etc/os-release is a symlink to
# usr/lib/os-release, so the real file is edited.
edit("usr/lib/os-release", set_keys({
    "PRETTY_NAME": f'"NoctraOS {version}"',
    "NAME": '"NoctraOS"',
    "VERSION": f'"{version}"',          # tools print NAME + VERSION: "NoctraOS 18.1" would be wrong
    "HOME_URL": '"https://noctraos.dev/"',
    "SUPPORT_URL": '"https://github.com/dazeb/noctraos/issues"',
    "BUG_REPORT_URL": '"https://github.com/dazeb/noctraos/issues"',
    "PRIVACY_POLICY_URL": '"https://noctraos.dev/"',
    "LOGO": "noctraos-logo",
}))
edit("etc/lsb-release", set_keys({"DISTRIB_DESCRIPTION": f'"NoctraOS {version}"'}))
edit("etc/issue", lambda t: t.replace("Zorin OS 18.1", f"NoctraOS {version}"))
edit("etc/issue.net", lambda t: t.replace("Zorin OS 18.1", f"NoctraOS {version}"))
edit("etc/legal", lambda t: t.replace("Zorin OS", "NoctraOS"))
edit("etc/update-motd.d/10-help-text", lambda t: t
     .replace("https://zorin.com\\n", "https://noctraos.dev\\n")
     .replace("Help:        https://help.zorin.com", "Help:        https://github.com/dazeb/noctraos"))

# The live session: host and user name (shown in terminals and the lock screen). FLAVOUR must
# stay non-empty or casper ignores both. The user is not "noctraos" so the unattended
# install's own account of that name never collides with it.
edit("etc/casper.conf", lambda t: t
     .replace('USERNAME="zorin"', 'USERNAME="live"')
     .replace('HOST="zorin"', 'HOST="noctraos"')
     .replace('FLAVOUR="Zorin OS"', 'FLAVOUR="NoctraOS"'))
(root / "etc/hostname").write_text("noctraos\n")

# Session names in the login screen's session picker.
for rel in ("usr/share/wayland-sessions/zorin.desktop", "usr/share/wayland-sessions/zorin-wayland.desktop",
            "usr/share/xsessions/zorin.desktop", "usr/share/xsessions/zorin-xorg.desktop"):
    edit(rel, lambda t: re.sub(r"(?m)^Name=Zorin Desktop", "Name=NoctraOS Desktop", t))

# Launchers that show up in the app grid but do nothing for NoctraOS: Zorin's upgrader would
# turn it into a different distribution, the rest are removed or replaced by module 04c on
# first boot (hiding them covers the time until it has run).
for name in ("com.zorin.desktop.upgrader", "zorin-appearance", "zorin-connect",
             "install-zorin-windows-app-support"):
    path = root / f"usr/share/applications/{name}.desktop"
    if path.exists():
        text = path.read_text()
        if "NoDisplay=true" not in text:
            path.write_text(re.sub(r"(?m)^\[Desktop Entry\]$", "[Desktop Entry]\nNoDisplay=true", text, count=1))

# Settings > Background lists wallpapers named after Zorin; leave the photographs, drop the
# "Zorin ..." entries, and add ours.
for xml in sorted((root / "usr/share/gnome-background-properties").glob("*.xml")):
    text = xml.read_text()
    new = re.sub(r"\s*<wallpaper(?: [^>]*)?>(?:(?!</wallpaper>).)*?<name>Zorin[^<]*</name>.*?</wallpaper>",
                 "", text, flags=re.S)
    if new != text:
        xml.write_text(new)
(root / "usr/share/gnome-background-properties/noctraos-wallpapers.xml").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE wallpapers SYSTEM "gnome-wp-list.dtd">\n'
    '<wallpapers>\n'
    '  <wallpaper>\n'
    '    <name>Ember Night</name>\n'
    '    <filename>/usr/share/backgrounds/noctraos/ember-night.jpg</filename>\n'
    '    <options>zoom</options>\n'
    '    <pcolor>#000000</pcolor>\n'
    '    <scolor>#000000</scolor>\n'
    '    <shade_type>solid</shade_type>\n'
    '  </wallpaper>\n'
    '</wallpapers>\n')
PY
  # Zorin's first-login tour ("Welcome to Zorin OS") would open on top of our own welcome; module 04c
  # removes the package later, this keeps it from ever starting on an installed system.
  rm -f "$root/etc/skel/.config/autostart/zorin-gnome-tour-autostart.desktop"
  # About page logo: os-release LOGO=noctraos-logo is looked up in the icon theme.
  f="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/assets/icons/noctraos-logo.svg"
  install -D -m 644 "$f" "$root/usr/share/icons/hicolor/scalable/apps/noctraos-logo.svg"
  install -D -m 644 "$f" "$root/usr/share/pixmaps/noctraos-logo.svg"
  # The Start button of Zorin's menu extension draws zorin-icon-symbolic.svg from its own folder.
  # Module 09's branding extension swaps it for the logo once provisioning has run; this covers the
  # live session and the first minutes of an installed system.
  local menu="$root/usr/share/gnome-shell/extensions/zorin-menu@zorinos.com"
  [ -f "$menu/zorin-icon-symbolic.svg" ] || { echo "rebrand: zorin-menu icon not found" >&2; return 1; }
  install -m 644 "$f" "$menu/zorin-icon-symbolic.svg"
  chroot "$root" gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
}
