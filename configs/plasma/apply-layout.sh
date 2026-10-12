#!/usr/bin/env bash
# Applies the NoctraOS Plasma panel layout once per account (marker plasma-layout-v1), from inside the Plasma session:
# plasmashell takes layout scripts over D-Bus only while it runs, so this is started by an autostart entry and waits for it.
# Delete ~/.config/noctraos/plasma-layout-v1 and run it again to re-apply.
set -u
MARKER="${XDG_CONFIG_HOME:-$HOME/.config}/noctraos/plasma-layout-v1"
SCRIPT="${NOCTRAOS_PLASMA_DIR:-/usr/local/share/noctraos/plasma}/panel-layout.js"
[ -f "$MARKER" ] && exit 0
[ -f "$SCRIPT" ] || { echo "no layout script: $SCRIPT" >&2; exit 1; }
qdbus="$(command -v qdbus6 || command -v qdbus-qt6 || true)"
[ -n "$qdbus" ] || { echo "qdbus6 is missing, the layout was not applied" >&2; exit 1; }
for _ in $(seq 1 60); do
  "$qdbus" org.kde.plasmashell /PlasmaShell >/dev/null 2>&1 && break
  sleep 2
done
"$qdbus" org.kde.plasmashell /PlasmaShell >/dev/null 2>&1 || { echo "plasmashell never answered, the layout was not applied" >&2; exit 1; }
if "$qdbus" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat "$SCRIPT")" >/dev/null; then
  mkdir -p "$(dirname "$MARKER")" && : > "$MARKER"
fi
