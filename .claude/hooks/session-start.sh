#!/bin/bash
# SessionStart hook for Claude Code cloud sessions. Installs what the unit tests and the shell checks need, so
# `python3 -B -m unittest discover -s tests` runs every test instead of skipping the ones whose tool is missing,
# and shellcheck is there for the CI shell job. Idempotent: each step checks first, a warm container does nothing.
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

YQ_VERSION=v4.54.1
SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo -n"

warn() { echo "session-start: $*" >&2; }

# apt: ssh-keygen (update signing tests), Xvfb + GTK 3 introspection + PyGObject (Control Panel smoke test),
# the shellcheck package (CI shell job), jq (noc JSON tests)
missing=()
command -v ssh-keygen >/dev/null || missing+=(openssh-client)
command -v xvfb-run >/dev/null || missing+=(xvfb)
command -v shellcheck >/dev/null || missing+=(shellcheck)
command -v jq >/dev/null || missing+=(jq)
for pkg in gir1.2-gtk-3.0 python3-gi; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  export DEBIAN_FRONTEND=noninteractive
  $SUDO apt-get update -qq >/dev/null 2>&1   # a broken third-party source must not stop the install below
  $SUDO apt-get install -y -qq "${missing[@]}" >/dev/null || warn "apt could not install: ${missing[*]}"
fi

# yq: the tests need mikefarah's v4; the apt package of the same name is a jq wrapper that rejects -o=json
if ! yq --version 2>/dev/null | grep -q mikefarah; then
  curl -sSfL -o /tmp/yq "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_amd64" \
    && $SUDO install -m 0755 /tmp/yq /usr/local/bin/yq || warn "could not install yq ${YQ_VERSION}"
  rm -f /tmp/yq
fi

# chromium: the site lightbox test drives headless Chrome; link Playwright's copy when the container has one
have_chrome=0
for browser in google-chrome chromium chromium-browser; do
  command -v "$browser" >/dev/null && have_chrome=1
done
if [ "$have_chrome" -eq 0 ]; then
  playwright_chrome=$(ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | sort -V | tail -1)
  if [ -n "$playwright_chrome" ]; then
    $SUDO ln -sf "$playwright_chrome" /usr/local/bin/chromium || warn "could not link chromium"
  else
    warn "no Chrome or Chromium found; the lightbox browser test will be skipped"
  fi
fi

exit 0
