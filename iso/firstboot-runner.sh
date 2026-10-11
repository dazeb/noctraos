#!/usr/bin/env bash
# noctraos first-boot provisioning — launched by the user's autostart entry.
# Prefers a fresh clone from GitHub; falls back to the baked-in snapshot.
set -u
DEST="$HOME/.local/share/noctraos"
MARKER="$DEST/.provisioned"
AUTOSTART="$HOME/.config/autostart/noctraos-setup.desktop"
LOG="$DEST-firstboot.log"
REPO_URL="https://github.com/dazeb/noctraos.git"
REPO_BRANCH="__NOCTRAOS_BRANCH__"   # substituted at ISO build time

if [ -f "$MARKER" ]; then rm -f "$AUTOSTART"; exit 0; fi
mkdir -p "$HOME/.local/share" "$(dirname "$LOG")"
echo "======================================================"
echo "  noctraos :: setting up your AI workstation"
echo "  (you will be asked for your password to install software)"
echo "======================================================"

# A fresh install has no git yet (module 01 installs it), so the latest code also comes as a tarball: curl is always there.
fetch_tarball() {
  local tmp
  tmp="$(mktemp -d)" || return 1
  if curl -fsSL --max-time 300 "${REPO_URL%.git}/archive/refs/heads/$REPO_BRANCH.tar.gz" | tar -xz -C "$tmp" --strip-components=1 \
     && [ -f "$tmp/install.sh" ]; then
    chmod 755 "$tmp" && mv "$tmp" "$DEST"
  else
    rm -rf "$tmp"
    return 1
  fi
}

rm -rf "$DEST"
if ! curl -fsSI --max-time 8 https://github.com >/dev/null 2>&1; then
  cp -r /opt/noctraos "$DEST"
  echo "noctraos: GitHub not reachable, using the provisioner snapshot baked into this ISO"
elif command -v git >/dev/null 2>&1 && git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$DEST" >/dev/null 2>&1; then
  echo "noctraos: provisioner fetched from GitHub (latest)"
elif rm -rf "$DEST" && fetch_tarball; then
  echo "noctraos: provisioner downloaded from GitHub (latest, without git)"
else
  rm -rf "$DEST"
  cp -r /opt/noctraos "$DEST"
  echo "noctraos: using the provisioner snapshot baked into this ISO"
fi

cd "$DEST"
# The welcome app runs while provisioning runs, so the wait becomes learning.
if [ -f "$DEST/bin/noctraos-welcome" ] && command -v python3 >/dev/null 2>&1; then
  ( setsid python3 "$DEST/bin/noctraos-welcome" --provisioning >/dev/null 2>&1 & )
fi
bash install.sh 2>&1 | tee "$LOG"
STATUS="${PIPESTATUS[0]}"
if [ "$STATUS" -eq 0 ]; then
  touch "$MARKER"
  rm -f "$AUTOSTART"
  echo "noctraos: setup complete — welcome aboard."
  echo "  Health check: noc doctor    GUI panel: noctraos-control"
else
  echo "noctraos: setup hit an error (exit $STATUS)."
  echo "  Log: $LOG    Re-run with: bash $DEST/install.sh"
fi
read -r -n 1 -s -p "Press any key to close this window..."
