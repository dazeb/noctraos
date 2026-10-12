#!/usr/bin/env bash
# Applies the NoctraOS Plasma panel layout once per account (marker plasma-layout-v1), from inside the Plasma session:
# plasmashell takes layout scripts over D-Bus only while it runs, so this is started by an autostart entry and waits for it.
# Delete ~/.config/noctraos/plasma-layout-v1 and run it again to re-apply.
set -u
MARKER="${XDG_CONFIG_HOME:-$HOME/.config}/noctraos/plasma-layout-v1"
SCRIPT="${NOCTRAOS_PLASMA_DIR:-/usr/local/share/noctraos/plasma}/panel-layout.js"
[ -f "$SCRIPT" ] || { echo "no layout script: $SCRIPT" >&2; exit 1; }

# Microsoft renamed VS Code's launcher; take whichever this machine has (NOCTRAOS_APP_DIRS: colon-separated, for tests).
vscode_launcher() {
  local d name
  IFS=: read -r -a dirs <<<"${NOCTRAOS_APP_DIRS:-/usr/share/applications:/usr/local/share/applications:$HOME/.local/share/applications:/var/lib/flatpak/exports/share/applications}"
  for name in com.microsoft.VSCode.desktop code.desktop; do
    for d in "${dirs[@]}"; do
      [ -f "$d/$name" ] && { printf '%s' "$name"; return 0; }
    done
  done
  printf 'code.desktop'
}
layout_script() { sed "s/@VSCODE_LAUNCHER@/$(vscode_launcher)/" "$SCRIPT"; }
if [ "${1:-}" = "--print-script" ]; then layout_script; exit 0; fi

[ -f "$MARKER" ] && exit 0
qdbus="$(command -v qdbus6 || command -v qdbus-qt6 || true)"
[ -n "$qdbus" ] || { echo "qdbus6 is missing, the layout was not applied" >&2; exit 1; }
for _ in $(seq 1 60); do
  "$qdbus" org.kde.plasmashell /PlasmaShell >/dev/null 2>&1 && break
  sleep 2
done
"$qdbus" org.kde.plasmashell /PlasmaShell >/dev/null 2>&1 || { echo "plasmashell never answered, the layout was not applied" >&2; exit 1; }
if "$qdbus" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(layout_script)" >/dev/null; then
  # The colour scheme is switched from inside the session as well: writing kdeglobals from the installer was not enough
  # to activate it on a running Plasma (seen on the Kubuntu VM), plasma-apply-colorscheme is.
  plasma-apply-colorscheme NoctraOSDark >/dev/null 2>&1 || echo "could not activate the NoctraOS colour scheme" >&2
  mkdir -p "$(dirname "$MARKER")" && : > "$MARKER"
fi
