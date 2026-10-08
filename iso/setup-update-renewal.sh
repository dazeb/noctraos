#!/usr/bin/env bash
# setup-update-renewal.sh — the weekly job that keeps the NoctraOS update manifests from expiring. A systemd USER timer, no sudo.
#
#   iso/setup-update-renewal.sh install     clone the repo for the job, write the units, enable the weekly timer
#   iso/setup-update-renewal.sh status      the timer, the last run and the real expiry of each public manifest
#   iso/setup-update-renewal.sh run         renew now (through the same unit, so the log is the same)
#   iso/setup-update-renewal.sh remove      disable and delete the timer (the clone stays)
#
# The job runs from its OWN clone of GitHub main (~/.local/share/noctraos-renew/repo, updated before every run), so it never depends on a
# development checkout or worktree that may be gone, and always uses the current publish scripts. It needs this workstation's
# ~/secrets/noctraos-update-signing and the store credentials, like iso/publish-update.sh. Weekly with Persistent=true: a run missed
# while the machine was off happens at the next boot. Manifests last 30 days, so one missed week is harmless; a month is not.
set -Eeuo pipefail

DIR="${RENEW_HOME:-$HOME/.local/share/noctraos-renew}"
REPO_URL="${RENEW_REPO_URL:-https://github.com/dazeb/noctraos.git}"
UNIT_DIR="${RENEW_UNIT_DIR:-$HOME/.config/systemd/user}"
BASE="${RENEW_CHECK_BASE:-https://dl.noctraos.dev/updates}"
say() { printf '%s\n' "$*"; }

install_units() {
  mkdir -p "$DIR" "$UNIT_DIR"
  [ -d "$DIR/repo/.git" ] || git clone -q "$REPO_URL" "$DIR/repo"
  cat > "$DIR/run.sh" <<RUN
#!/usr/bin/env bash
set -Eeuo pipefail
git -C "$DIR/repo" fetch -q origin main
git -C "$DIR/repo" reset -q --hard origin/main
exec bash "$DIR/repo/iso/renew-update-channels.sh"
RUN
  chmod 755 "$DIR/run.sh"
  cat > "$UNIT_DIR/noctraos-update-renewal.service" <<UNIT
[Unit]
Description=Renew the NoctraOS update manifests (they expire after 30 days)

[Service]
Type=oneshot
ExecStart=$DIR/run.sh
Environment=SHLVL=2
TimeoutStartSec=30min
UNIT
  cat > "$UNIT_DIR/noctraos-update-renewal.timer" <<UNIT
[Unit]
Description=Weekly renewal of the NoctraOS update manifests

[Timer]
OnCalendar=Mon *-*-* 04:30
Persistent=true
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
UNIT
  systemctl --user daemon-reload
}

case "${1:-}" in
  install)
    command -v jq >/dev/null && command -v git >/dev/null && command -v rclone >/dev/null || { say "needs git, jq and rclone" >&2; exit 1; }
    [ -r "${NOCTRAOS_UPDATE_KEY:-$HOME/secrets/noctraos-update-signing}" ] || { say "no signing key at ~/secrets/noctraos-update-signing" >&2; exit 1; }
    install_units
    systemctl --user enable --now noctraos-update-renewal.timer >/dev/null
    say "installed: $(systemctl --user list-timers noctraos-update-renewal.timer --no-legend | awk '{print "next run", $1, $2, $3}')" ;;
  status)
    systemctl --user is-enabled noctraos-update-renewal.timer 2>&1 | sed 's/^/timer:  /'
    systemctl --user list-timers noctraos-update-renewal.timer --no-legend 2>/dev/null | awk '{print "next:   " $1, $2, $3}'
    systemctl --user show noctraos-update-renewal.service -p ActiveEnterTimestamp -p Result 2>/dev/null | sed 's/^/last:   /'
    for ch in nightly stable; do
      printf 'public %-8s ' "$ch"
      curl -fsS --max-time 20 "$BASE/$ch/manifest.json" 2>/dev/null | jq -r '"serial \(.serial), expires \(.expires)"' 2>/dev/null || echo "no manifest"
    done ;;
  run) systemctl --user start noctraos-update-renewal.service && say "renewed (see: journalctl --user -u noctraos-update-renewal -n 20)" ;;
  remove)
    systemctl --user disable --now noctraos-update-renewal.timer 2>/dev/null || true
    rm -f "$UNIT_DIR/noctraos-update-renewal.service" "$UNIT_DIR/noctraos-update-renewal.timer"
    systemctl --user daemon-reload; say "removed" ;;
  *) say "usage: setup-update-renewal.sh install|status|run|remove" >&2; exit 2 ;;
esac
