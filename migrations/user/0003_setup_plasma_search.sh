#!/usr/bin/env bash
# desktops: plasma
# Accounts not present during the update catch up using the same once-per-account
# helper as module 09 and KDE autostart. Never reset settings or its done marker.
set -u

if [ "${NOCTRAOS_FLAVOUR:-zorin}" != kubuntu ]; then
  echo "NOT APPLIED on the ${NOCTRAOS_FLAVOUR:-zorin} flavour: Plasma search shortcut is for the Plasma flavour"
  exit 0
fi

MARKER="${XDG_CONFIG_HOME:-$HOME/.config}/noctraos/plasma-search-v1"
[ -f "$MARKER" ] && exit 0
SETUP=/usr/local/share/noctraos/plasma/apply-search.sh
if [ ! -x "$SETUP" ]; then
  echo "WARN: Plasma search shortcut helper is missing; KDE autostart will catch up later" >&2
  exit 0
fi

# Use installed code only, with this account's HOME and session bus. Without a
# running session the helper leaves its marker absent, so autostart can retry.
NOCTRAOS_SEARCH_PLASMA=/usr/local/bin/noctraos-search-plasma "$SETUP" \
  || echo "WARN: Plasma search shortcut was not set; KDE autostart will retry" >&2
exit 0
