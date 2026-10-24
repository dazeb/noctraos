#!/usr/bin/env bash
# apply-search.sh — the per-account half of Super+Space on KDE Plasma (flavour kubuntu): adds Meta+Space to
# KRunner's global shortcut, keeping the shortcuts it already has. KGlobalAccel is asked to do it (its own
# API, and it finds KRunner's component and action itself), so it applies at once and survives a restart.
# Started by /etc/xdg/autostart/noctraos-plasma-search.desktop; once per account (marker plasma-search-v1).
# Delete ~/.config/noctraos/plasma-search-v1 and run it again to re-apply.
set -u
MARKER="${XDG_CONFIG_HOME:-$HOME/.config}/noctraos/plasma-search-v1"
SETUP="${NOCTRAOS_SEARCH_PLASMA:-/usr/local/bin/noctraos-search-plasma}"
[ -f "$MARKER" ] && exit 0
[ -x "$SETUP" ] || { echo "apply-search.sh: $SETUP is missing" >&2; exit 1; }

if "$SETUP" --setup; then
  mkdir -p "$(dirname "$MARKER")" && : > "$MARKER"
else
  # Not fatal: Alt+Space still opens KRunner, and System Settings > Shortcuts can set Meta+Space by hand.
  echo "apply-search.sh: could not add Super+Space; set it in System Settings > Shortcuts" >&2
  exit 1
fi
