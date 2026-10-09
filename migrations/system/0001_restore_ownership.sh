#!/usr/bin/env bash
# Give back the owners and groups that NoctraOS images built before the fix lost.
#
# iso/build-noctraos-iso.sh repacked the system with `mksquashfs -all-root`, so every file in the image became root:root. That
# broke things that need a group or a service user: the D-Bus launch helper (root:messagebus, mode 4754) cannot be run by the bus,
# so the Software Updater's apt daemon never starts ("Failed to execute program org.debian.apt: Permission denied") and the
# updater freezes; /etc/shadow, the crontab and ssh-agent programs, the polkit and man-page cache directories, and the log
# files lost theirs too. A machine installed from such an image keeps that until this runs.
#
# It only runs on a NoctraOS system that really came from such an image: /etc/noctraos-release must exist AND one of a few
# known files (the launch helper, crontab, unix_chkpwd, chage) must still be exactly root:root, which no healthy install is
# (they are root:messagebus, root:crontab, root:shadow there). A one-line install onto stock Ubuntu is therefore left alone.
#
# The list is configs/ownership/zorin-18.1-core.tsv (path, user, group, flag). Only a file that is exactly root:root is touched,
# so an owner someone set on purpose is kept. Modes were never lost, but chown clears setuid/setgid on executables (even as
# root), so each mode is read first and put back after. Idempotent: a second run finds nothing that is still root:root.
set -uo pipefail

SNAPSHOT="${NOCTRAOS_SNAPSHOT:-/usr/local/share/noctraos/repo}"
MANIFEST="$SNAPSHOT/configs/ownership/zorin-18.1-core.tsv"
PREFIX="" FLAT="root:root" CHOWN=chown LOOKUP=1
if [ -n "${NOC_TEST_HOOKS:-}" ]; then      # stand-ins for tests only; root never honours them otherwise
  PREFIX="${NOC_OWNERSHIP_ROOT:-}" FLAT="${NOC_OWNERSHIP_FLATTENED:-root:root}" CHOWN="${NOC_OWNERSHIP_CHOWN:-chown}"
  [ -n "${NOC_OWNERSHIP_NO_LOOKUP:-}" ] && LOOKUP=0
fi

[ -f "$MANIFEST" ] || { echo "noctraos: no ownership list in this snapshot, nothing to do"; exit 0; }

# Evidence first: a NoctraOS system, and at least one canary that is still flattened.
CANARIES=(/usr/lib/dbus-1.0/dbus-daemon-launch-helper /usr/bin/crontab /usr/sbin/unix_chkpwd /usr/bin/chage)
flattened_image() {
  [ -f "$PREFIX/etc/noctraos-release" ] || return 1
  local c
  for c in "${CANARIES[@]}"; do
    [ -e "$PREFIX$c" ] && [ "$(stat -c %U:%G -- "$PREFIX$c" 2>/dev/null)" = "$FLAT" ] && return 0
  done
  return 1
}
flattened_image || { echo "noctraos: this system's files already have their owners, nothing to do"; exit 0; }

fixed=0 failed=0

known() { [ "$LOOKUP" = 0 ] || { getent passwd "$1" >/dev/null && getent group "$2" >/dev/null; }; }

# restore <path> <user> <group>: only for a file that still has the flattened owner.
restore() {
  local path="$PREFIX$1" user="$2" group="$3" mode
  [ -e "$path" ] || [ -L "$path" ] || return 0
  [ "$(stat -c %U:%G -- "$path" 2>/dev/null)" = "$FLAT" ] || return 0
  known "$user" "$group" || return 0
  mode="$(stat -c %a -- "$path")"
  if "$CHOWN" -h "$user:$group" -- "$path"; then
    [ -L "$path" ] || chmod "$mode" -- "$path"        # chown dropped setuid/setgid: put the mode back
    fixed=$((fixed + 1))
  else
    echo "noctraos: could not change the owner of $1"
    failed=$((failed + 1))
  fi
}

while IFS=$'\t' read -r path user group flag; do
  case "$path" in ''|'#'*) continue ;; esac
  if [ "$flag" = R ]; then
    known "$user" "$group" || continue
    [ -d "$PREFIX$path" ] || continue
    # Directories and plain files only (the man cache has no setuid programs); nothing is followed out of the tree.
    n="$(find "$PREFIX$path" -xdev -user "${FLAT%%:*}" -group "${FLAT##*:}" \( -type d -o -type f \) -print | wc -l)"
    if find "$PREFIX$path" -xdev -user "${FLAT%%:*}" -group "${FLAT##*:}" \( -type d -o -type f \) -exec "$CHOWN" -h "$user:$group" {} +; then
      fixed=$((fixed + n))
    else
      echo "noctraos: could not change every owner below $path"
      failed=$((failed + 1))
    fi
  else
    restore "$path" "$user" "$group"
  fi
done < "$MANIFEST"

echo "noctraos: restored the owner of $fixed file(s) and folder(s)"
# A failure (immutable file, read-only mount, ...) must not be recorded as done: the updater retries a failed migration, and
# the D-Bus launch helper staying root:root would keep the Software Updater broken. Everything else was still processed above.
if [ "$failed" -gt 0 ]; then
  echo "noctraos: $failed change(s) failed; this will be tried again at the next update"
  exit 1
fi
exit 0
