#!/usr/bin/env bash
# noctraos bootstrapper.
#
#   curl -fsSL https://<RAW-BOOTSTRAP-URL>/boot.sh | bash
#
# Clones (or updates) the provisioner into ~/.local/share/noctraos and runs it.
# Override the source with: NOCTRAOS_REPO_URL=git@... NOCTRAOS_BRANCH=dev ./boot.sh
set -euo pipefail

REPO_URL="${NOCTRAOS_REPO_URL:-https://github.com/dazeb/noctraos.git}"
BRANCH="${NOCTRAOS_BRANCH:-main}"
DEST="${NOCTRAOS_HOME:-$HOME/.local/share/noctraos}"

if [ "$(id -u)" -eq 0 ]; then
  echo "boot.sh: do not run as root — run as your normal desktop user." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git curl
fi

echo "== noctraos: fetching provisioner ($BRANCH) =="
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch origin "$BRANCH"
  git -C "$DEST" reset --hard "origin/$BRANCH"
else
  rm -rf "$DEST"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$DEST"
fi

cd "$DEST"
exec bash install.sh "$@"
