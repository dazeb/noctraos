#!/usr/bin/env bash
# Pin the NoctraOS Control Panel to the dock (the favorites the taskbar shows) on accounts made before it was pinned by
# default. Runs once per account; a person who unpins it afterwards keeps that choice, because the updater records this
# migration as done. A fresh install pins it in install/desktop/gnome/06_desktop_theme.sh.
set -u
ID=noctraos-control.desktop
# Where module 06/07 install launchers (tests point this at a temp directory).
APPS="${NOCTRAOS_APPLICATIONS_DIR:-/usr/local/share/applications}"

# The dock is the GNOME desktop's (zorin flavour). Elsewhere there is nothing to pin, and failing would make the updater retry
# this at every update and login, so it reports that and counts as done.
if [ "${NOCTRAOS_FLAVOUR:-zorin}" != zorin ]; then
  echo "NOT APPLIED on the ${NOCTRAOS_FLAVOUR} flavour: the Control Panel dock pin is for the GNOME dock"
  exit 0
fi

current="$(gsettings get org.gnome.shell favorite-apps 2>/dev/null)" || { echo "no desktop settings yet; retrying later" >&2; exit 1; }
case "$current" in *"'$ID'"*) exit 0 ;; esac

# Without the launcher a dock icon would be a blank question mark; module 06 installs it, so try again at the next login.
if [ ! -f "$APPS/$ID" ]; then
  echo "$ID is not installed yet; retrying later" >&2
  exit 1
fi

case "$current" in
  '@as []'|'[]') new="['$ID']" ;;
  *) new="${current%]}, '$ID']" ;;
esac
gsettings set org.gnome.shell favorite-apps "$new" || { echo "could not pin the Control Panel" >&2; exit 1; }
